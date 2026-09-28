"""Runner behaviour end to end: real adapters and store, mocked network."""

import json
from pathlib import Path

import httpx
from tenacity import wait_none

from asteria.config import CountryCatalogue, SourceCatalogue
from asteria.ingest.http import HttpFetcher
from asteria.ingest.raw_store import RawStore
from asteria.ingest.runner import run_ingest, write_run_manifest
from asteria.sources import build_adapters

CATALOGUE = SourceCatalogue.model_validate(
    {
        "providers": {
            "eurostat": {
                "name": "E",
                "base_url": "https://es.test",
                "licence": "CC BY 4.0",
                "terms_url": "t",
            },
            "worldbank": {
                "name": "W",
                "base_url": "https://wb.test",
                "licence": "CC BY 4.0",
                "terms_url": "t",
            },
        },
        "history_start": "2019-01",
        "indicators": [
            {
                "id": "rate",
                "provider": "eurostat",
                "dataset": "ds_rate",
                "lens": "labour_supply",
                "title": "t",
                "frequency": "M",
                "unit": "u",
                "filters": {"unit": "PC"},
            },
            {
                "id": "gdp",
                "provider": "worldbank",
                "dataset": "GDP",
                "lens": "economic_cycle",
                "title": "t",
                "frequency": "A",
                "unit": "u",
                "filters": {},
            },
        ],
    }
)

EUROSTAT_OK = json.dumps(
    {
        "id": ["unit", "geo", "time"],
        "size": [1, 2, 1],
        "updated": "2026-09-22",
        "dimension": {
            "unit": {"category": {"index": {"PC": 0}}},
            "geo": {"category": {"index": {"EL": 0, "IE": 1}}},
            "time": {"category": {"index": {"2025-01": 0}}},
        },
        "value": {"0": 9.1, "1": 4.2},
    }
).encode()


def fetcher(routes: dict[str, httpx.Response]) -> HttpFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes[request.url.host]

    return HttpFetcher(httpx.Client(transport=httpx.MockTransport(handler)), 2, wait_none())


def test_one_failing_source_does_not_stop_or_corrupt_the_others(
    tmp_path: Path, countries: CountryCatalogue
) -> None:
    store = RawStore(tmp_path)
    adapters = build_adapters(CATALOGUE)
    routes = {"es.test": httpx.Response(200, content=EUROSTAT_OK), "wb.test": httpx.Response(503)}

    report = run_ingest(CATALOGUE, countries, adapters, store, "live", fetcher(routes))

    by_id = {o.indicator_id: o for o in report.outcomes}
    assert by_id["rate"].status == "ok" and by_id["rate"].change == "created"
    assert by_id["gdp"].status == "failed"
    assert by_id["gdp"].error_type == "TransientSourceError"
    assert "503" in (by_id["gdp"].error or "")
    assert store.read("eurostat", "rate")[0] == EUROSTAT_OK


def test_invalid_payload_never_replaces_good_evidence(
    tmp_path: Path, countries: CountryCatalogue
) -> None:
    store = RawStore(tmp_path)
    adapters = build_adapters(CATALOGUE)
    ok = {"es.test": httpx.Response(200, content=EUROSTAT_OK)}
    run_ingest(CATALOGUE, countries, adapters, store, "live", fetcher(ok), only=["rate"])

    broken = {"es.test": httpx.Response(200, content=b"<html>maintenance</html>")}
    report = run_ingest(
        CATALOGUE, countries, adapters, store, "live", fetcher(broken), only=["rate"]
    )

    assert report.outcomes[0].error_type == "SourceContractError"
    assert store.read("eurostat", "rate")[0] == EUROSTAT_OK


def test_replay_needs_no_network_and_reports_coverage_gaps(
    tmp_path: Path, countries: CountryCatalogue
) -> None:
    store = RawStore(tmp_path)
    adapters = build_adapters(CATALOGUE)
    ok = {"es.test": httpx.Response(200, content=EUROSTAT_OK)}
    run_ingest(CATALOGUE, countries, adapters, store, "live", fetcher(ok), only=["rate"])

    report = run_ingest(CATALOGUE, countries, adapters, store, "replay", only=["rate"])

    outcome = report.outcomes[0]
    assert outcome.change == "replayed"
    assert set(outcome.coverage) == {"EL", "IE"}
    assert any("no values for" in w and "BG" in w for w in outcome.warnings)
    manifest = json.loads(write_run_manifest(report, tmp_path / "runs").read_text())
    assert manifest["outcomes"][0]["sha256"] == outcome.sha256
