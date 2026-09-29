"""Curation of the real starter pack and committed snapshots."""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from asteria.config import ROOT, CountryCatalogue, SourceCatalogue, WorkforceConfig
from asteria.curate.pipeline import EXPORTS, CurateReport, run_curate
from asteria.ingest.raw_store import RawStore
from asteria.sources import build_adapters

STORE = RawStore(ROOT / "data" / "raw-or-fixtures" / "sources")


def curate(out: Path, catalogue: SourceCatalogue, countries: CountryCatalogue,
           workforce: WorkforceConfig) -> CurateReport:  # fmt: skip
    adapters = build_adapters(catalogue, date(2026, 9, 28))
    return run_curate(out, catalogue, countries, workforce, adapters, STORE)


@pytest.fixture(scope="module")
def report(
    tmp_path_factory: pytest.TempPathFactory,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
) -> CurateReport:
    from asteria.config import load_workforce

    return curate(
        tmp_path_factory.mktemp("c"), catalogue, countries, load_workforce(ROOT / "config")
    )


def test_counts_match_the_independent_profile(report: CurateReport) -> None:
    """Figures from docs/data_profile.md, produced by a separate pandas script."""
    counts = {r.rule_id: r.rows_affected for r in report.rules}
    assert report.workforce_rows_read == 2407
    assert report.employees == 2400
    assert counts["WF_EXACT_DUPLICATE"] == 7
    assert counts["WF_COUNTRY_ALIAS"] == 8
    assert counts["WF_COUNTRY_MISSING"] == 9
    assert counts["WF_CAREER_LEVEL_ALIAS"] == 10
    assert counts["WF_HIRE_DATE_MISSING"] == 5
    assert counts["WF_TERMINATION_BEFORE_HIRE"] == 5
    assert counts["WF_TERMINATION_TYPE_MISSING"] == 13
    assert counts["WF_REGRETTED_UNKNOWN"] == 2
    assert counts["WF_EOC_ON_PERMANENT"] == 90
    assert report.measurable == 2390
    assert report.in_country_scope == 2381


def test_quality_gate_passes(report: CurateReport) -> None:
    assert report.gate_failures == []
    assert report.missing_indicators == []


def test_no_value_is_spread_to_a_finer_frequency(report: CurateReport) -> None:
    """Frequency integrity: one value per native period, spanning the whole period."""
    con = duckdb.connect(report.db_path, read_only=True)
    bad = con.execute(
        """
        SELECT indicator_id, frequency, count(*) FROM external_observations
        WHERE date_diff('month', period_start, period_end + 1)
              <> CASE frequency WHEN 'M' THEN 1 WHEN 'Q' THEN 3 ELSE 12 END
        GROUP BY ALL
        """
    ).fetchall()
    assert bad == []
    dupes = con.execute(
        "SELECT count(*) FROM (SELECT 1 FROM external_observations"
        " GROUP BY indicator_id, country_code, release_code, period_start HAVING count(*) > 1)"
    ).fetchone()
    assert dupes == (0,)


def test_rerun_is_byte_identical(
    tmp_path: Path,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
    report: CurateReport,
) -> None:
    from asteria.config import load_workforce

    again = curate(tmp_path, catalogue, countries, load_workforce(ROOT / "config"))
    for name in [*EXPORTS, "quality_report"]:
        first = Path(report.outputs[name]).read_bytes()
        assert Path(again.outputs[name]).read_bytes() == first, name
