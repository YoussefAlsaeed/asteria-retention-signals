"""Curate stage: build the canonical layer in DuckDB and export reviewable evidence.

The database is rebuilt from scratch on every run (intentional full overwrite), from
inputs that are themselves checksummed, so reruns produce byte-identical exports.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from importlib.resources import files
from pathlib import Path

import duckdb
import pandas as pd

from asteria.config import CountryCatalogue, SourceCatalogue, WorkforceConfig
from asteria.curate.quality import RULES
from asteria.ingest.raw_store import RawStore, RawStoreError, sha256_hex
from asteria.sources.base import SourceAdapter, SourceError

log = logging.getLogger(__name__)

WORKFORCE_COLUMNS = [
    "employee_id", "country_code", "business_unit", "job_family", "career_level",
    "employment_type", "hire_date", "termination_date", "termination_type",
    "regretted_exit", "source_system", "record_updated_at",
]  # fmt: skip

DB_FILENAME = "asteria.duckdb"


class CurateError(Exception):
    """An input needed by the curate stage is missing or malformed."""


@dataclass
class RuleCount:
    rule_id: str
    domain: str
    severity: str
    description: str
    rows_affected: int


@dataclass
class CurateReport:
    db_path: str
    workforce_source: str
    workforce_source_sha256: str
    workforce_rows_read: int
    employees: int
    measurable: int
    in_country_scope: int
    external_values: int
    rules: list[RuleCount]
    missing_indicators: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)

    @property
    def gate_failures(self) -> list[RuleCount]:
        return [r for r in self.rules if r.severity == "error" and r.rows_affected > 0]


def run_curate(
    curated_dir: Path,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
    workforce: WorkforceConfig,
    adapters: dict[str, SourceAdapter],
    store: RawStore,
) -> CurateReport:
    curated_dir.mkdir(parents=True, exist_ok=True)
    db_path = curated_dir / DB_FILENAME
    for stale in (db_path, db_path.with_name(DB_FILENAME + ".wal")):
        stale.unlink(missing_ok=True)

    source = workforce.source_path()
    con = duckdb.connect(str(db_path))
    try:
        _load_config_tables(con, catalogue, countries, workforce)
        rows_read, source_sha = _load_workforce(con, source)
        missing = _load_external(con, catalogue, adapters, store)
        con.execute(_sql("workforce.sql"))
        con.execute(_sql("external.sql"))

        report = CurateReport(
            db_path=str(db_path),
            workforce_source=source.name,
            workforce_source_sha256=source_sha,
            workforce_rows_read=rows_read,
            employees=_scalar(con, "SELECT count(*) FROM employees"),
            measurable=_scalar(con, "SELECT count(*) FROM employees WHERE is_measurable"),
            in_country_scope=_scalar(con, "SELECT count(*) FROM employees WHERE in_country_scope"),
            external_values=_scalar(con, "SELECT count(*) FROM external_observations"),
            rules=_rule_counts(con),
            missing_indicators=missing,
        )
        report.outputs = _export(con, curated_dir)
    finally:
        con.close()

    report.outputs["quality_report"] = _write_quality_report(report, curated_dir)
    for rule in report.gate_failures:
        log.error("quality gate failed", extra={"rule": rule.rule_id, "rows": rule.rows_affected})
    return report


def _sql(name: str) -> str:
    return files("asteria.curate").joinpath("sql", name).read_text(encoding="utf-8")


def _scalar(con: duckdb.DuckDBPyConnection, query: str) -> int:
    row = con.execute(query).fetchone()
    return int(row[0]) if row else 0


def _load_config_tables(
    con: duckdb.DuckDBPyConnection,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
    workforce: WorkforceConfig,
) -> None:
    con.execute("CREATE TABLE cfg_params (as_of_date DATE)")
    con.execute("INSERT INTO cfg_params VALUES (?)", [workforce.as_of_date])

    con.execute("CREATE TABLE cfg_country_alias (code VARCHAR PRIMARY KEY, canonical VARCHAR)")
    con.executemany(
        "INSERT INTO cfg_country_alias VALUES (?, ?)", sorted(countries.by_alias.items())
    )

    con.execute("CREATE TABLE cfg_level_alias (label VARCHAR PRIMARY KEY, canonical VARCHAR)")
    if workforce.career_level_aliases:
        con.executemany(
            "INSERT INTO cfg_level_alias VALUES (?, ?)",
            sorted(workforce.career_level_aliases.items()),
        )

    con.execute("CREATE TABLE cfg_allowed (field VARCHAR, value VARCHAR)")
    con.executemany(
        "INSERT INTO cfg_allowed VALUES (?, ?)",
        [(f, v) for f, values in workforce.allowed.model_dump().items() for v in values],
    )

    con.execute(
        "CREATE TABLE cfg_rules (rule_id VARCHAR PRIMARY KEY, domain VARCHAR, severity VARCHAR,"
        " description VARCHAR, position INTEGER)"
    )
    con.executemany(
        "INSERT INTO cfg_rules VALUES (?, ?, ?, ?, ?)",
        [(r.id, r.domain, r.severity, r.description, i) for i, r in enumerate(RULES)],
    )

    con.execute(
        "CREATE TABLE cfg_geo_map (provider VARCHAR, geo VARCHAR, country_code VARCHAR,"
        " PRIMARY KEY (provider, geo))"
    )
    con.executemany(
        "INSERT INTO cfg_geo_map VALUES (?, ?, ?)",
        [("eurostat", c.eurostat, c.code) for c in countries.countries]
        + [("worldbank", c.worldbank, c.code) for c in countries.countries],
    )

    con.execute(
        "CREATE TABLE cfg_indicators (indicator_id VARCHAR PRIMARY KEY, lens VARCHAR,"
        " title VARCHAR, unit VARCHAR, frequency VARCHAR)"
    )
    con.executemany(
        "INSERT INTO cfg_indicators VALUES (?, ?, ?, ?, ?)",
        [(i.id, i.lens, i.title, i.unit, i.frequency) for i in catalogue.indicators],
    )


def _load_workforce(con: duckdb.DuckDBPyConnection, source: Path) -> tuple[int, str]:
    """Load the CSV as text, exactly as supplied. Typing happens in SQL where it is audited."""
    try:
        content = source.read_bytes()
    except FileNotFoundError as exc:
        raise CurateError(f"workforce file not found: {source}") from exc
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    missing = [c for c in WORKFORCE_COLUMNS if c not in frame.columns]
    if missing:
        raise CurateError(f"{source.name} is missing columns {missing}")
    frame = frame[WORKFORCE_COLUMNS]
    frame.insert(0, "source_row", range(2, len(frame) + 2))  # file line number (header = 1)
    con.register("raw_workforce_df", frame)
    con.execute("CREATE TABLE raw_workforce AS SELECT * FROM raw_workforce_df")
    con.unregister("raw_workforce_df")
    return len(frame), sha256_hex(content)


def _load_external(
    con: duckdb.DuckDBPyConnection,
    catalogue: SourceCatalogue,
    adapters: dict[str, SourceAdapter],
    store: RawStore,
) -> list[str]:
    """Parse stored snapshots into source-shaped rows.

    A missing or unreadable snapshot is reported, not fatal.
    """
    con.execute(
        """
        CREATE TABLE stg_external (
            indicator_id VARCHAR, provider VARCHAR, dataset VARCHAR, frequency VARCHAR,
            geo VARCHAR, source_period VARCHAR, value DOUBLE, status VARCHAR, status_label VARCHAR,
            release_code VARCHAR, source_updated VARCHAR, fetched_at VARCHAR,
            snapshot_sha256 VARCHAR
        )
        """
    )
    missing = []
    rows: list[tuple[object, ...]] = []
    for indicator in catalogue.indicators:
        try:
            content, meta = store.read(indicator.provider, indicator.id)
            parsed = adapters[indicator.provider].parse(content, indicator)
        except (RawStoreError, SourceError) as exc:
            log.warning(
                "indicator unavailable", extra={"indicator": indicator.id, "error": str(exc)}
            )
            missing.append(indicator.id)
            continue
        rows += [
            (
                indicator.id, indicator.provider, indicator.dataset, indicator.frequency,
                o.geo, o.period, o.value, o.status,
                parsed.status_labels.get(o.status) if o.status else None,
                o.dimensions.get("release"),
                parsed.source_updated, meta.fetched_at, meta.sha256,
            )
            for o in parsed.observations
        ]  # fmt: skip
    if rows:
        # One bulk insert: row-by-row executemany commits per row and is very slow on disk.
        columns = [c[0] for c in con.execute("DESCRIBE stg_external").fetchall()]
        frame = pd.DataFrame(rows, columns=columns).astype({"value": "float64"})
        con.register("stg_external_df", frame)
        con.execute("INSERT INTO stg_external SELECT * FROM stg_external_df")
        con.unregister("stg_external_df")
    return missing


def _rule_counts(con: duckdb.DuckDBPyConnection) -> list[RuleCount]:
    rows = con.execute(
        """
        WITH hits AS (
            SELECT rule_id, count(*) AS n FROM wf_quality_events GROUP BY rule_id
            UNION ALL
            SELECT rule_id, count(*) AS n FROM ex_quality_events GROUP BY rule_id
        )
        SELECT r.rule_id, r.domain, r.severity, r.description, coalesce(sum(h.n), 0)
        FROM cfg_rules AS r LEFT JOIN hits AS h USING (rule_id)
        GROUP BY r.rule_id, r.domain, r.severity, r.description, r.position
        ORDER BY r.position
        """
    ).fetchall()
    return [
        RuleCount(
            rule_id=r[0], domain=r[1], severity=r[2], description=r[3], rows_affected=int(r[4])
        )
        for r in rows
    ]


EXPORTS = {
    "employees": "SELECT * REPLACE (array_to_string(quality_rules, '|') AS quality_rules)"
    " FROM employees ORDER BY employee_id",
    "external_observations": "SELECT * REPLACE (array_to_string(quality_rules, '|') AS"
    " quality_rules) FROM external_observations"
    " ORDER BY indicator_id, country_code, release_code NULLS FIRST, period_start",
    "external_coverage": "SELECT * FROM external_coverage"
    " ORDER BY indicator_id, country_code, release_code NULLS FIRST",
    "quality_events": "SELECT 'workforce' AS domain, rule_id, employee_id AS record_key,"
    " CAST(source_row AS VARCHAR) AS detail FROM wf_quality_events"
    " UNION ALL SELECT 'external', rule_id, indicator_id || ':' || geo, source_period"
    " || coalesce(':' || release_code, '') FROM ex_quality_events"
    " ORDER BY domain DESC, rule_id, record_key, detail",
}


def _export(con: duckdb.DuckDBPyConnection, curated_dir: Path) -> dict[str, str]:
    outputs = {}
    for name, query in EXPORTS.items():
        path = curated_dir / f"{name}.csv"
        con.execute(f"COPY ({query}) TO '{path.as_posix()}' (HEADER, DELIMITER ',')")
        outputs[name] = str(path)
    return outputs


def _write_quality_report(report: CurateReport, curated_dir: Path) -> str:
    json_path = curated_dir / "quality_report.json"
    payload = asdict(report)
    payload.pop("db_path")
    payload.pop("outputs")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Data quality report",
        "",
        "Generated by `asteria curate`. Rule definitions: `src/asteria/curate/quality.py`.",
        "",
        "## Workforce",
        "",
        f"- Source: `{report.workforce_source}` (SHA-256 `{report.workforce_source_sha256[:16]}…`)",
        f"- Rows read: {report.workforce_rows_read}",
        f"- Canonical employees: {report.employees}",
        f"- Measurable (no excluding rule): {report.measurable}",
        f"- In country scope (also has a known country): {report.in_country_scope}",
        "",
        "## External",
        "",
        f"- Canonical values: {report.external_values}",
        f"- Indicators unavailable: {', '.join(report.missing_indicators) or 'none'}",
        "",
        "## Rules",
        "",
        "| Rule | Domain | Severity | Rows | Meaning |",
        "|---|---|---|---:|---|",
        *(
            f"| `{r.rule_id}` | {r.domain} | {r.severity} | {r.rows_affected} | {r.description} |"
            for r in report.rules
        ),
        "",
        f"Quality gate: **{'FAILED' if report.gate_failures else 'passed'}**"
        + (
            f" ({', '.join(r.rule_id for r in report.gate_failures)})"
            if report.gate_failures
            else ""
        ),
        "",
    ]
    md_path = curated_dir / "quality_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(md_path)
