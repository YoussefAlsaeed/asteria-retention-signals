"""Period semantics, gaps, and the quality gate for external indicators."""

import json

from asteria.config import SourceCatalogue
from tests.curate.conftest import CurateFn, jsonstat

MONTHLY = {"freq": "M", "s_adj": "SA", "age": "TOTAL", "sex": "T", "unit": "PC_ACT"}
QUARTERLY = {"freq": "Q", "s_adj": "NSA", "indic_em": "JVR", "nace_r2_1": "B-T",
             "sizeclas": "TOTAL"}  # fmt: skip


def only(catalogue: SourceCatalogue, *ids: str) -> SourceCatalogue:
    return catalogue.model_copy(
        update={"indicators": [i for i in catalogue.indicators if i.id in ids]}
    )


def test_periods_get_real_bounds_by_frequency(run: CurateFn, catalogue: SourceCatalogue) -> None:
    gdp = json.dumps(
        [{"pages": 1, "lastupdated": "2026-07-13"},
         [{"indicator": {"id": "NY.GDP.MKTP.KD.ZG"}, "countryiso3code": "GRC", "date": "2024",
           "value": 2.1}]]
    ).encode()  # fmt: skip
    snapshots = {
        ("eurostat", "unemployment_rate"): jsonstat(MONTHLY, ["EL"], ["2024-02"], {0: 9.0}),
        ("eurostat", "job_vacancy_rate"): jsonstat(QUARTERLY, ["EL"], ["2024-Q4"], {0: 1.3}),
        ("worldbank", "gdp_growth"): gdp,
    }
    cat = only(catalogue, "unemployment_rate", "job_vacancy_rate", "gdp_growth")
    _, con = run(snapshots=snapshots, catalogue_override=cat)

    got = con.execute(
        "SELECT indicator_id, country_code, frequency, period_start::VARCHAR, period_end::VARCHAR"
        " FROM external_observations ORDER BY indicator_id"
    ).fetchall()
    assert got == [
        ("gdp_growth", "GR", "A", "2024-01-01", "2024-12-31"),
        ("job_vacancy_rate", "GR", "Q", "2024-10-01", "2024-12-31"),
        ("unemployment_rate", "GR", "M", "2024-02-01", "2024-02-29"),  # leap year
    ]


def test_gap_inside_a_series_is_reported(run: CurateFn, catalogue: SourceCatalogue) -> None:
    payload = jsonstat(MONTHLY, ["EL"], ["2024-01", "2024-02", "2024-03"], {0: 9.0, 2: 8.8})
    report, con = run(snapshots={("eurostat", "unemployment_rate"): payload},
                      catalogue_override=only(catalogue, "unemployment_rate"))  # fmt: skip

    gaps = con.execute(
        "SELECT source_period FROM ex_quality_events WHERE rule_id = 'EX_PERIOD_GAP'"
    ).fetchall()
    assert gaps == [("2024-02-01",)]
    assert con.execute("SELECT gaps FROM external_coverage").fetchone() == (1,)
    assert not report.gate_failures  # a gap is a warning, not a failure


def test_unmapped_country_fails_the_quality_gate(run: CurateFn, catalogue: SourceCatalogue) -> None:
    payload = jsonstat(MONTHLY, ["EL", "XK"], ["2024-01"], {0: 9.0, 1: 12.0})
    report, con = run(snapshots={("eurostat", "unemployment_rate"): payload},
                      catalogue_override=only(catalogue, "unemployment_rate"))  # fmt: skip

    assert [r.rule_id for r in report.gate_failures] == ["EX_GEO_UNMAPPED"]
    # The unmapped row never reaches the canonical table.
    assert con.execute("SELECT count(*) FROM external_observations").fetchone() == (1,)


def test_missing_snapshot_is_reported_not_fatal(run: CurateFn, catalogue: SourceCatalogue) -> None:
    report, _ = run(catalogue_override=only(catalogue, "unemployment_rate"))
    assert report.missing_indicators == ["unemployment_rate"]
    assert not report.gate_failures
