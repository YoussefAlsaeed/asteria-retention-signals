"""Service boundary: response contracts, validation, and the error contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from asteria.api.repository import Repository


def test_health_ok(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "detail": None}


def test_meta_describes_every_filter(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert [o["objective_id"] for o in meta["objectives"]] == [
        "NEW_HIRE_6M", "REGRETTED_TURNOVER_12M", "SENIOR_HIRE_12M"]  # fmt: skip
    assert {c["code"] for c in meta["countries"]} == {"GR", "RO", "PL", "IT", "IE", "BG"}
    assert meta["segments"] == ["Digital", "Finance", "Sales", "Supply Chain"]
    assert len(meta["signals"]) == 5
    senior = next(o for o in meta["objectives"] if o["objective_id"] == "SENIOR_HIRE_12M")
    assert senior["variants"] == ["main", "sensitivity_manager"]
    assert senior["target"] == 0.9


def test_measures_return_the_pipeline_numbers(client: TestClient) -> None:
    body = client.get("/api/objectives/SENIOR_HIRE_12M/measures?grain=year").json()
    first = body["points"][0]
    assert (first["period_start"], first["numerator"], first["denominator"]) == (
        "2021-01-01",
        48,
        65,
    )
    assert first["status"] == "not_met" and first["confidence"] == "clear"
    assert body["points"][-1]["status"] == "pending" and body["points"][-1]["rate"] is None
    assert [p["period_start"] for p in body["points"]] == sorted(
        p["period_start"] for p in body["points"]
    )


def test_status_gives_latest_measured_period_per_objective(client: TestClient) -> None:
    tiles = {t["objective_id"]: t for t in client.get("/api/status?grain=year").json()}
    assert set(tiles) == {"NEW_HIRE_6M", "REGRETTED_TURNOVER_12M", "SENIOR_HIRE_12M"}
    assert all(t["status"] != "pending" for t in tiles.values())
    assert tiles["NEW_HIRE_6M"]["period_start"] == "2024-01-01"  # 2025 cohorts still pending
    assert tiles["NEW_HIRE_6M"]["pending_periods"] == 1


def test_signals_never_describe_a_period_after_the_month_they_were_known(
    client: TestClient,
) -> None:
    series = client.get("/api/signals/gdp_growth").json()
    assert len(series) == 6
    for s in series:
        for p in s["points"]:
            if p["value"] is not None:
                assert p["signal_period_end"] < p["as_of_date"]
                assert p["signal_age_days"] > 0


def test_associations_and_cells(client: TestClient) -> None:
    rows = client.get("/api/objectives/NEW_HIRE_6M/associations").json()
    assert len(rows) == 10  # 5 signals x (naive, within_country)
    cells = client.get("/api/objectives/NEW_HIRE_6M/associations/unemployment_rate/cells").json()
    assert cells and all(c["n"] > 0 and 0 <= c["event_rate"] <= 1 for c in cells)


def test_trust_reports_sources_and_quality(client: TestClient) -> None:
    trust = client.get("/api/trust").json()
    assert trust["workforce"] == {"employees": 2400, "measurable": 2390, "in_country_scope": 2381}
    assert {p["licence"] for p in trust["providers"]} == {"CC BY 4.0"}
    rules = {r["rule_id"]: r["rows_affected"] for r in trust["quality_rules"]}
    assert rules["WF_EXACT_DUPLICATE"] == 7


@pytest.mark.parametrize(
    ("path", "status", "fragment"),
    [
        ("/api/objectives/NOPE/measures", 404, "Unknown objective"),
        ("/api/signals/NOPE", 404, "Unknown signal"),
        ("/api/status?country=XX", 422, "country must be ALL"),
        ("/api/status?segment=Marketing", 422, "segment must be All"),
        ("/api/objectives/NEW_HIRE_6M/measures?variant=sensitivity_manager", 422, "variant"),
        ("/api/objectives/NEW_HIRE_6M/measures?grain=week", 422, "month"),
    ],
)
def test_invalid_input_is_a_clear_client_error(
    client: TestClient, path: str, status: int, fragment: str
) -> None:
    response = client.get(path)
    assert response.status_code == status
    assert fragment in str(response.json()["detail"])


def test_missing_data_is_503_with_the_fix(empty_client: TestClient) -> None:
    assert empty_client.get("/api/health").json()["status"] == "data_missing"
    response = empty_client.get("/api/status")
    assert response.status_code == 503
    assert "asteria run" in response.json()["detail"]


def test_unexpected_error_is_500_without_internals(
    built_data_dir: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from asteria.api.app import create_app
    from asteria.config import Settings
    from asteria.context import load_context

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(Repository, "latest_status", boom)
    app = create_app(load_context(Settings(data_dir=built_data_dir)))  # type: ignore[arg-type]
    response = TestClient(app, raise_server_exceptions=False).get("/api/status")
    assert response.status_code == 500
    assert "request id" in response.json()["detail"]
    assert "secret" not in response.text


def test_api_responses_are_not_cached_and_dashboard_is_served(client: TestClient) -> None:
    assert client.get("/api/meta").headers["cache-control"] == "no-store"
    page = client.get("/")
    assert page.status_code == 200 and "Retention signals" in page.text
