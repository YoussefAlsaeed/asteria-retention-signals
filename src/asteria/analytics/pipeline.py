"""Analyse stage: objective measures, point-in-time signals, and association models.

Reads the canonical layer built by `asteria curate` and adds `mart_*` tables to the same
DuckDB file: the consumption-ready analytical product used by the API and dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from importlib.resources import files
from pathlib import Path

import duckdb
import pandas as pd

from asteria.analytics.association import AssociationResult, fit_associations
from asteria.config import AnalysisConfig, WorkforceConfig
from asteria.curate.pipeline import DB_FILENAME
from asteria.domain.objectives import ObjectiveSpec

log = logging.getLogger(__name__)


class AnalyseError(Exception):
    """The analyse stage cannot run (usually: curate has not been run)."""


@dataclass
class ObjectiveHeadline:
    objective_id: str
    period: str
    rate: float | None
    target: float
    direction: str
    status: str
    confidence: str | None
    denominator: float


@dataclass
class AnalyseReport:
    headlines: list[ObjectiveHeadline]
    associations: list[AssociationResult]
    outputs: dict[str, str] = field(default_factory=dict)


EXPORTS = {
    "objective_measures": "SELECT * FROM mart_objective_measures ORDER BY objective_id, variant,"
    " grain, country_code, segment_value, period_start",
    "signal_asof": "SELECT * FROM mart_signal_asof ORDER BY indicator_id, country_code, as_of_date",
    "association_results": "SELECT * FROM mart_association_results ORDER BY objective_id,"
    " indicator_id, model",
    "association_cells": "SELECT * FROM mart_association_cells ORDER BY objective_id,"
    " indicator_id, country_code, period_start",
}


def run_analyse(
    curated_dir: Path,
    analysis: AnalysisConfig,
    workforce: WorkforceConfig,
    objectives: list[ObjectiveSpec],
) -> AnalyseReport:
    db_path = curated_dir / DB_FILENAME
    if not db_path.exists():
        raise AnalyseError(f"{db_path} not found; run `asteria curate` first")

    con = duckdb.connect(str(db_path))
    try:
        _load_config(con, analysis, workforce, objectives)
        con.execute(f"CREATE OR REPLACE VIEW emp AS SELECT *, {analysis.segment} AS segment_value"
                    " FROM employees")  # fmt: skip  # segment is a validated Literal
        con.execute(_sql("retention.sql"))
        con.execute(_sql("signals.sql"))

        start = pd.Timestamp(f"{analysis.reporting_start}-01")
        frame = _model_frame(con)
        associations = fit_associations(frame, start)
        columns = [f.name for f in fields(AssociationResult)]
        rows = [asdict(a) for a in associations]
        _store(con, "mart_association_results", pd.DataFrame(rows, columns=columns))
        _store(con, "mart_association_cells", _cells(frame))

        report = AnalyseReport(headlines=_headlines(con), associations=associations)
        report.outputs = _export(con, curated_dir)
    finally:
        con.close()
    report.outputs["analysis_summary"] = _write_summary(report, curated_dir)
    return report


def _sql(name: str) -> str:
    return files("asteria.analytics").joinpath("sql", name).read_text(encoding="utf-8")


def _load_config(
    con: duckdb.DuckDBPyConnection,
    analysis: AnalysisConfig,
    workforce: WorkforceConfig,
    objectives: list[ObjectiveSpec],
) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE cfg_analysis AS SELECT ?::DATE AS as_of_date,"
        " ?::DATE AS reporting_start, ?::INTEGER AS min_sample",
        [workforce.as_of_date, date.fromisoformat(f"{analysis.reporting_start}-01"),
         analysis.min_sample],
    )  # fmt: skip
    _store(
        con,
        "cfg_objectives",
        pd.DataFrame(
            [(o.objective_id, o.measure, o.months, o.direction, o.target, o.effective_to)
             for o in objectives],
            columns=["objective_id", "measure", "months", "direction", "target", "effective_to"],
        ),
    )  # fmt: skip
    levels = []
    for o in objectives:
        variants = {"main": o.levels, "sensitivity_manager": o.sensitivity_levels}
        for variant, chosen in variants.items():
            if variant != "main" and chosen is None:
                continue
            for level in chosen or workforce.allowed.career_level:
                levels.append((o.objective_id, variant, level))
    _store(
        con,
        "cfg_objective_levels",
        pd.DataFrame(levels, columns=["objective_id", "variant", "level"]),
    )
    _store(
        con,
        "cfg_signals",
        pd.DataFrame(
            [(s.indicator, s.release, s.lag_days) for s in analysis.signals],
            columns=["indicator_id", "release_code", "lag_days"],
        ).astype({"release_code": "string"}),
    )


def _store(con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame) -> None:
    con.register("_frame", frame)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _frame")
    con.unregister("_frame")


def _model_frame(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Person-level outcomes joined to the signal known at the start of the relevant month."""
    return con.execute(
        """
        SELECT m.objective_id, s.indicator_id, m.country_key AS country_code,
               m.cohort_month AS as_of_date, m.lost::INTEGER AS event, s.value
        FROM mart_cohort_members AS m
        JOIN mart_signal_asof AS s
            ON s.country_code = m.country_key AND s.as_of_date = m.cohort_month
        WHERE m.variant = 'main' AND m.cohort_mature AND m.country_key <> '(unassigned)'
        UNION ALL
        SELECT 'REGRETTED_TURNOVER_12M', s.indicator_id, p.country_key, p.month_start,
               p.regretted_exit::INTEGER, s.value
        FROM mart_person_months AS p
        JOIN mart_signal_asof AS s
            ON s.country_code = p.country_key AND s.as_of_date = p.month_start
        CROSS JOIN cfg_analysis AS c
        WHERE p.month_start >= c.reporting_start AND p.country_key <> '(unassigned)'
        ORDER BY 1, 2, 3, 4
        """
    ).df()


def _cells(frame: pd.DataFrame) -> pd.DataFrame:
    """Country x quarter points for the dashboard's relationship view (with sample size)."""
    df = frame.dropna(subset=["value"]).copy()
    if df.empty:
        columns = ["objective_id", "indicator_id", "country_code", "period_start", "n",
                   "events", "signal_mean", "event_rate"]  # fmt: skip
        return pd.DataFrame(columns=columns)
    df["period_start"] = pd.to_datetime(df["as_of_date"]).dt.to_period("Q").dt.start_time.dt.date
    cells = (
        df.groupby(["objective_id", "indicator_id", "country_code", "period_start"])
        .agg(n=("event", "size"), events=("event", "sum"), signal_mean=("value", "mean"))
        .reset_index()
    )
    cells["event_rate"] = (cells["events"] / cells["n"]).round(6)
    cells["signal_mean"] = cells["signal_mean"].round(6)
    return cells


def _headlines(con: duckdb.DuckDBPyConnection) -> list[ObjectiveHeadline]:
    rows = con.execute(
        """
        SELECT objective_id, strftime(period_start, '%Y'), rate, target, direction, status,
               confidence, denominator
        FROM mart_objective_measures
        WHERE variant = 'main' AND grain = 'year' AND country_code = 'ALL'
          AND segment_value = 'All'
        ORDER BY objective_id, period_start
        """
    ).fetchall()
    return [
        ObjectiveHeadline(r[0], r[1], None if r[2] is None else round(r[2], 4), r[3], r[4],
                          r[5], r[6], round(r[7], 1))
        for r in rows
    ]  # fmt: skip


def _export(con: duckdb.DuckDBPyConnection, curated_dir: Path) -> dict[str, str]:
    outputs = {}
    for name, query in EXPORTS.items():
        path = curated_dir / f"{name}.csv"
        con.execute(f"COPY ({query}) TO '{path.as_posix()}' (HEADER, DELIMITER ',')")
        outputs[name] = str(path)
    return outputs


def _write_summary(report: AnalyseReport, curated_dir: Path) -> str:
    def pct(v: float | None) -> str:
        return "-" if v is None else f"{v:.1%}"

    def num(v: float | None) -> str:
        return "-" if v is None else f"{v:.3g}"

    lines = [
        "# Analysis summary",
        "",
        "Generated by `asteria analyse`. Definitions: `config/analysis.yaml`;"
        " SQL: `src/asteria/analytics/sql/`.",
        "",
        "## Objectives, company-wide, by year",
        "",
        "| Objective | Year | Rate | Target | Status | Confidence | Denominator |",
        "|---|---|---:|---:|---|---|---:|",
        *(
            f"| `{h.objective_id}` | {h.period} | {pct(h.rate)} | "
            f"{'≥' if h.direction == 'at_least' else '≤'} {h.target:.1%} | {h.status} | "
            f"{h.confidence or '-'} | {h.denominator:g} |"
            for h in report.headlines
        ),
        "",
        "Cohort objectives: year = hire year. Turnover: year = trailing 12 months to December.",
        "",
        "## Signal associations",
        "",
        "Odds ratio per one within-country standard deviation of the signal. `within_country`"
        " adds country fixed effects and a time trend; q = Benjamini-Hochberg across all"
        " within-country tests. Association, not causation.",
        "",
        "| Objective | Signal | Model | n | Events | OR | 95% CI | p | q |",
        "|---|---|---|---:|---:|---:|---|---:|---:|",
        *(
            f"| `{a.objective_id}` | `{a.indicator_id}` | {a.model} | {a.n_obs} | {a.n_events} | "
            f"{num(a.odds_ratio)} | {num(a.ci_low)}–{num(a.ci_high)} | {num(a.p_value)} | "
            f"{num(a.q_value)} |" + (f" {a.note}" if a.note else "")
            for a in report.associations
        ),
        "",
    ]
    path = curated_dir / "analysis_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
