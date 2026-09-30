"""The real analysis, checked against an independent pandas computation and time rules."""

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from asteria.analytics.pipeline import AnalyseReport, run_analyse
from asteria.config import ROOT, CountryCatalogue, SourceCatalogue, load_analysis, load_workforce
from asteria.curate.pipeline import run_curate
from asteria.domain.objectives import ObjectiveRule, load_objectives
from asteria.ingest.raw_store import RawStore
from asteria.sources import build_adapters

STORE = RawStore(ROOT / "data" / "raw-or-fixtures" / "sources")


@pytest.fixture(scope="module")
def report(
    tmp_path_factory: pytest.TempPathFactory,
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
) -> AnalyseReport:
    out = tmp_path_factory.mktemp("real")
    workforce = load_workforce(ROOT / "config")
    analysis = load_analysis(ROOT / "config", catalogue)
    rules = {
        k: ObjectiveRule(v.measure, v.months, tuple(v.levels) if v.levels else None,
                         tuple(v.sensitivity_levels) if v.sensitivity_levels else None)
        for k, v in analysis.objectives.items()
    }  # fmt: skip
    run_curate(out, catalogue, countries, workforce, build_adapters(catalogue, date(2026, 9, 28)),
               STORE)  # fmt: skip
    return run_analyse(out, analysis, workforce, load_objectives(analysis.objectives_path(), rules))


@pytest.fixture(scope="module")
def con(report: AnalyseReport) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(Path(report.outputs["objective_measures"]).parent / "asteria.duckdb"),
                          read_only=True)  # fmt: skip


def independent(report: AnalyseReport) -> dict[str, float]:
    """Same definitions, computed with pandas date offsets instead of SQL."""
    e = pd.read_csv(Path(report.outputs["objective_measures"]).parent / "employees.csv",
                    parse_dates=["hire_date", "exit_date"])  # fmt: skip
    e = e[e.is_measurable]

    def cohort(months: int, levels: list[str] | None = None) -> float:
        c = e[e.hire_date.dt.year == 2021]
        c = c[c.career_level.isin(levels)] if levels else c
        lost = c.exit_date.notna() & (c.exit_date < c.hire_date + pd.DateOffset(months=months))
        return float(1 - lost.mean())

    ends = pd.date_range("2021-01-31", "2021-12-31", freq="ME")
    headcount = sum(((e.hire_date <= d) & (e.exit_date.isna() | (e.exit_date > d))).sum()
                    for d in ends) / 12  # fmt: skip
    regretted = ((e.regretted_status == "regretted") & (e.exit_date.dt.year == 2021)).sum()
    return {
        "NEW_HIRE_6M": cohort(6),
        "SENIOR_HIRE_12M": cohort(12, ["Senior Leader"]),
        "REGRETTED_TURNOVER_12M": float(regretted / headcount),
    }


def test_2021_headlines_match_independent_computation(report: AnalyseReport) -> None:
    expected = independent(report)
    got = {h.objective_id: h.rate for h in report.headlines if h.period == "2021"}
    for objective_id, value in expected.items():
        assert got[objective_id] == pytest.approx(value, abs=1e-4), objective_id


def test_no_signal_is_used_before_it_is_published(con: duckdb.DuckDBPyConnection) -> None:
    leaks = con.execute(
        "SELECT count(*) FROM mart_signal_asof WHERE available_from > as_of_date"
    ).fetchone()
    assert leaks == (0,)


def test_carried_values_keep_their_own_period(con: duckdb.DuckDBPyConnection) -> None:
    row = con.execute(
        "SELECT signal_frequency, signal_period_start::VARCHAR, signal_period_end::VARCHAR"
        " FROM mart_signal_asof WHERE indicator_id = 'gdp_growth' AND country_code = 'GR'"
        " AND as_of_date = DATE '2023-03-01'"
    ).fetchone()
    assert row == ("A", "2021-01-01", "2021-12-31")  # 2022 not yet published in March 2023


def test_publication_lag_is_applied(con: duckdb.DuckDBPyConnection) -> None:
    """Dec-2022 unemployment becomes usable 62 days after 31 Dec, i.e. not by 1 March 2023."""
    row = con.execute(
        "SELECT signal_period_start::VARCHAR FROM mart_signal_asof"
        " WHERE indicator_id = 'unemployment_rate' AND country_code = 'GR'"
        " AND as_of_date = DATE '2023-03-01'"
    ).fetchone()
    assert row == ("2022-11-01",)


def test_every_model_fitted_and_is_corrected_for_multiple_tests(report: AnalyseReport) -> None:
    within = [a for a in report.associations if a.model == "within_country"]
    assert len(within) == 15  # 3 objectives x 5 signals
    assert all(a.odds_ratio is not None and a.q_value is not None for a in within)


def test_cohort_maturity_equals_the_clarified_per_person_rule(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Clarification Q2: include a hire only when hire date + N months <= 31 Dec 2025.

    The pipeline decides maturity per monthly cohort; on this data (as-of = a month end)
    both rules must select exactly the same people.
    """
    disagreements = con.execute(
        """
        SELECT count(*) FROM mart_cohort_members
        WHERE cohort_mature <> ((hire_date + to_months(
            CASE objective_id WHEN 'NEW_HIRE_6M' THEN 6 ELSE 12 END))::DATE <= DATE '2025-12-31')
        """
    ).fetchone()
    assert disagreements == (0,)
