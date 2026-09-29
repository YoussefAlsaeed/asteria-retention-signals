from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import duckdb
import pytest

from asteria.config import (
    ROOT,
    CountryCatalogue,
    SourceCatalogue,
    WorkforceConfig,
    load_workforce,
)
from asteria.curate.pipeline import CurateReport, run_curate
from asteria.ingest.raw_store import RawStore, SnapshotMeta, sha256_hex
from asteria.sources import build_adapters

HEADER = (
    "employee_id,country_code,business_unit,job_family,career_level,employment_type,"
    "hire_date,termination_date,termination_type,regretted_exit,source_system,record_updated_at"
)

CurateFn = Callable[..., tuple[CurateReport, duckdb.DuckDBPyConnection]]


@pytest.fixture
def workforce_config() -> WorkforceConfig:
    return load_workforce(ROOT / "config")


@pytest.fixture
def run(
    tmp_path: Path,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
    workforce_config: WorkforceConfig,
) -> CurateFn:
    """Run the curate stage on a CSV body and optional snapshots; return report + DB."""

    def _run(
        csv_rows: list[str] | None = None,
        snapshots: dict[tuple[str, str], bytes] | None = None,
        catalogue_override: SourceCatalogue | None = None,
    ) -> tuple[CurateReport, duckdb.DuckDBPyConnection]:
        cat = catalogue_override or catalogue
        source = tmp_path / "events.csv"
        source.write_text("\n".join([HEADER, *(csv_rows or [])]) + "\n", encoding="utf-8")
        config = workforce_config.model_copy(update={"source_file": source})
        store = RawStore(tmp_path / "sources")
        for (provider, indicator_id), content in (snapshots or {}).items():
            store.write(content, _meta(provider, indicator_id, content))
        report = run_curate(
            tmp_path / "curated",
            cat,
            countries,
            config,
            build_adapters(cat, date(2026, 9, 28)),
            store,
        )
        return report, duckdb.connect(report.db_path, read_only=True)

    return _run


def _meta(provider: str, indicator_id: str, content: bytes) -> SnapshotMeta:
    return SnapshotMeta(
        provider=provider, indicator_id=indicator_id, dataset="d", request_url="u",
        request_params=[], fetched_at="2026-09-28T00:00:00+00:00", http_status=200,
        sha256=sha256_hex(content), bytes=len(content), source_updated=None, observation_count=0,
    )  # fmt: skip


def jsonstat(filters: dict[str, str], geos: list[str], periods: list[str],
             values: dict[int, float]) -> bytes:  # fmt: skip
    dims = {**{k: [v] for k, v in filters.items()}, "geo": geos, "time": periods}
    return json.dumps(
        {
            "id": list(dims),
            "size": [len(v) for v in dims.values()],
            "dimension": {
                d: {"category": {"index": {c: i for i, c in enumerate(v)}}} for d, v in dims.items()
            },
            "value": {str(k): v for k, v in values.items()},
        }
    ).encode()
