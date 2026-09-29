"""Objective measures on a tiny workforce whose answers were computed by hand."""

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from asteria.analytics.pipeline import AnalyseError, run_analyse
from asteria.config import ROOT, CountryCatalogue, SourceCatalogue, load_analysis, load_workforce
from asteria.curate.pipeline import run_curate
from asteria.domain.objectives import ObjectiveRule, load_objectives
from asteria.ingest.raw_store import RawStore
from asteria.sources import build_adapters
from tests.curate.conftest import HEADER

ROWS = [
    # R1: exits the day before the 6-month anniversary (2023-07-31) -> lost
    "R1,GR,Sales,Field Sales,Individual Contributor,Permanent,2023-01-31,2023-07-30,Voluntary,false,HCM_A,2025-12-20",
    # R2: exits on the anniversary -> employed through it -> retained
    "R2,GR,Sales,Field Sales,Individual Contributor,Permanent,2023-01-31,2023-07-31,Voluntary,false,HCM_A,2025-12-20",
    "R3,GR,Sales,Field Sales,Individual Contributor,Permanent,2023-01-15,,,,HCM_A,2025-12-20",
    # R4: senior, regretted exit after ~5 months
    "R4,GR,Sales,Field Sales,Senior Leader,Permanent,2023-01-10,2023-06-01,Voluntary,true,HCM_A,2025-12-20",
    "R5,GR,Sales,Field Sales,Manager,Permanent,2023-01-20,,,,HCM_A,2025-12-20",
    # R6: unknown country -> company-wide only
    "R6,,Sales,Field Sales,Individual Contributor,Permanent,2023-01-05,,,,HCM_A,2025-12-20",
    # R7: hired 2025-07 -> 6-month window not complete at 2025-12-31
    "R7,GR,Sales,Field Sales,Individual Contributor,Permanent,2025-07-01,,,,HCM_A,2025-12-20",
    # R8: 2020 hire -> outside cohorts, inside headcount and turnover
    "R8,GR,Sales,Field Sales,Individual Contributor,Permanent,2020-06-01,2021-03-15,Voluntary,true,HCM_A,2025-12-20",
]  # fmt: skip


@pytest.fixture(scope="module")
def db(
    tmp_path_factory: pytest.TempPathFactory,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
) -> duckdb.DuckDBPyConnection:
    tmp = tmp_path_factory.mktemp("analyse")
    source = tmp / "events.csv"
    source.write_text("\n".join([HEADER, *ROWS]) + "\n", encoding="utf-8")
    workforce = load_workforce(ROOT / "config").model_copy(update={"source_file": source})
    analysis = load_analysis(ROOT / "config", catalogue)
    rules = {
        k: ObjectiveRule(v.measure, v.months, tuple(v.levels) if v.levels else None,
                         tuple(v.sensitivity_levels) if v.sensitivity_levels else None)
        for k, v in analysis.objectives.items()
    }  # fmt: skip
    objectives = load_objectives(analysis.objectives_path(), rules)
    curated = tmp / "curated"
    adapters = build_adapters(catalogue, date(2026, 9, 28))
    run_curate(curated, catalogue, countries, workforce, adapters, RawStore(tmp / "none"))
    report = run_analyse(curated, analysis, workforce, objectives)
    return duckdb.connect(report.outputs["objective_measures"].replace(
        "objective_measures.csv", "asteria.duckdb"), read_only=True)  # fmt: skip


def measure(con: duckdb.DuckDBPyConnection, **where: str) -> dict[str, Any]:
    clause = " AND ".join(f"{k} = ?" for k in where)
    cursor = con.execute(
        f"SELECT * FROM mart_objective_measures WHERE {clause}", list(where.values())
    )
    rows = cursor.fetchall()
    assert len(rows) == 1, (where, rows)
    return dict(zip([d[0] for d in cursor.description], rows[0], strict=True))


def test_anniversary_boundary_and_company_slice(db: duckdb.DuckDBPyConnection) -> None:
    m = measure(db, objective_id="NEW_HIRE_6M", variant="main", grain="month",
                period_start="2023-01-01", country_code="ALL", segment_value="All")  # fmt: skip
    assert (m["numerator"], m["denominator"]) == (4, 6)  # R2, R3, R5, R6 retained
    assert m["status"] == "insufficient_sample"  # 6 < min_sample


def test_country_slice_excludes_unknown_country(db: duckdb.DuckDBPyConnection) -> None:
    m = measure(db, objective_id="NEW_HIRE_6M", variant="main", grain="month",
                period_start="2023-01-01", country_code="GR", segment_value="All")  # fmt: skip
    assert (m["numerator"], m["denominator"]) == (3, 5)


def test_senior_scope_and_manager_sensitivity(db: duckdb.DuckDBPyConnection) -> None:
    main = measure(
        db,
        objective_id="SENIOR_HIRE_12M",
        variant="main",
        grain="month",
        period_start="2023-01-01",
        country_code="ALL",
        segment_value="All",
    )
    sens = measure(db, objective_id="SENIOR_HIRE_12M", variant="sensitivity_manager",
                   grain="month", period_start="2023-01-01", country_code="ALL",
                   segment_value="All")  # fmt: skip
    assert (main["numerator"], main["denominator"]) == (0, 1)
    assert (sens["numerator"], sens["denominator"]) == (1, 2)


def test_immature_cohort_is_pending_without_a_rate(db: duckdb.DuckDBPyConnection) -> None:
    m = measure(db, objective_id="NEW_HIRE_6M", variant="main", grain="month",
                period_start="2025-07-01", country_code="ALL", segment_value="All")  # fmt: skip
    assert m["status"] == "pending" and m["rate"] is None
    year = measure(db, objective_id="NEW_HIRE_6M", variant="main", grain="year",
                   period_start="2025-01-01", country_code="GR", segment_value="All")  # fmt: skip
    assert year["status"] == "pending"


def test_2020_hires_are_not_cohorts(db: duckdb.DuckDBPyConnection) -> None:
    rows = db.execute(
        "SELECT count(*) FROM mart_cohort_members WHERE employee_id = 'R8'"
    ).fetchone()
    assert rows == (0,)


def test_trailing_turnover_numerator_and_mean_month_end_headcount(
    db: duckdb.DuckDBPyConnection,
) -> None:
    """2023: one regretted exit (R4). Month-end headcounts: Jan-May 6, Jun 5, Jul-Dec 3."""
    m = measure(db, objective_id="REGRETTED_TURNOVER_12M", variant="main", grain="year",
                period_start="2023-01-01", country_code="ALL", segment_value="All")  # fmt: skip
    assert m["numerator"] == 1
    assert m["denominator"] == pytest.approx((5 * 6 + 5 + 6 * 3) / 12)
    assert str(m["period_end"]) == "2023-12-31"


def test_2020_hire_counts_in_early_turnover(db: duckdb.DuckDBPyConnection) -> None:
    m = measure(db, objective_id="REGRETTED_TURNOVER_12M", variant="main", grain="year",
                period_start="2021-01-01", country_code="GR", segment_value="All")  # fmt: skip
    assert m["numerator"] == 1  # R8, exit 2021-03-15
    assert m["denominator"] == pytest.approx(2 / 12)  # employed at Jan and Feb month ends


def test_wilson_interval_known_value(db: duckdb.DuckDBPyConnection) -> None:
    low, high = db.execute("SELECT wilson_low(5.0, 10.0), wilson_high(5.0, 10.0)").fetchone()  # type: ignore[misc]
    assert (round(low, 4), round(high, 4)) == (0.2366, 0.7634)


def test_missing_database_explains_what_to_run(tmp_path: Path, catalogue: SourceCatalogue) -> None:
    analysis = load_analysis(ROOT / "config", catalogue)
    with pytest.raises(AnalyseError, match="asteria curate"):
        run_analyse(tmp_path, analysis, load_workforce(ROOT / "config"), [])


def test_interval_is_undefined_when_numerator_exceeds_denominator(
    db: duckdb.DuckDBPyConnection,
) -> None:
    """Regression: 1 exit over an average headcount of 1/6 once crashed the Wilson macro."""
    assert db.execute("SELECT wilson_low(1.0, 0.1667), wilson_high(1.0, 0.1667)").fetchone() == (
        None,
        None,
    )
