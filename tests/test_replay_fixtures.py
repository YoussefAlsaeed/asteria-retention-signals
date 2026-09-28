"""The committed source snapshots must replay cleanly: this is the reviewer's offline path."""

import pytest

from asteria.config import ROOT, CountryCatalogue, SourceCatalogue
from asteria.ingest.raw_store import RawStore
from asteria.ingest.runner import IngestReport, run_ingest
from asteria.sources import build_adapters

STORE = RawStore(ROOT / "data" / "raw-or-fixtures" / "sources")


@pytest.fixture(scope="module")
def report(catalogue: SourceCatalogue, countries: CountryCatalogue) -> IngestReport:
    return run_ingest(catalogue, countries, build_adapters(catalogue), STORE, "replay")


def test_every_configured_indicator_replays(report: IngestReport) -> None:
    failures = {o.indicator_id: o.error for o in report.failed}
    assert failures == {}


def test_every_indicator_covers_all_six_countries(report: IngestReport) -> None:
    for outcome in report.outcomes:
        assert len(outcome.coverage) == 6, (outcome.indicator_id, sorted(outcome.coverage))


def test_history_spans_the_workforce_horizon(report: IngestReport) -> None:
    """Brief: about three years of history; we need 2021-2025 plus look-back."""
    for outcome in report.outcomes:
        for geo, cov in outcome.coverage.items():
            assert cov.first_period is not None and cov.first_period[:4] <= "2020", (
                outcome.indicator_id,
                geo,
            )
            assert cov.last_period is not None and cov.last_period[:4] >= "2025", (
                outcome.indicator_id,
                geo,
            )
