import json
from typing import Any

import pytest

from asteria.config import CountryCatalogue, Indicator
from asteria.sources.base import SourceContractError
from asteria.sources.worldbank import WorldBankAdapter

ADAPTER = WorldBankAdapter("https://example.test/v2", end_year=2026)


def row(geo: str, year: str, value: float | None, ind: str = "NY.GDP.MKTP.KD.ZG") -> dict[str, Any]:
    return {
        "indicator": {"id": ind},
        "countryiso3code": geo,
        "date": year,
        "value": value,
        "obs_status": "",
    }


def payload(rows: list[dict[str, Any]] | None, pages: int = 1) -> bytes:
    return json.dumps([{"page": 1, "pages": pages, "lastupdated": "2026-07-13"}, rows]).encode()


def test_parses_rows_and_keeps_nulls_as_missing(worldbank_indicator: Indicator) -> None:
    parsed = ADAPTER.parse(
        payload([row("IRL", "2025", 12.3), row("IRL", "2026", None)]), worldbank_indicator
    )
    assert [(o.geo, o.period, o.value, o.status) for o in parsed.observations] == [
        ("IRL", "2025", 12.3, None),
        ("IRL", "2026", None, None),
    ]
    assert parsed.source_updated == "2026-07-13"


def test_no_data_rows_is_an_empty_result(worldbank_indicator: Indicator) -> None:
    assert ADAPTER.parse(payload(None), worldbank_indicator).observations == []


def test_multiple_pages_are_refused_not_truncated(worldbank_indicator: Indicator) -> None:
    with pytest.raises(SourceContractError, match="2 pages"):
        ADAPTER.parse(payload([row("IRL", "2025", 1.0)], pages=2), worldbank_indicator)


def test_error_message_payload_is_a_contract_error(worldbank_indicator: Indicator) -> None:
    body = json.dumps([{"message": [{"id": "120", "value": "Invalid value"}]}]).encode()
    with pytest.raises(SourceContractError, match="Invalid value"):
        ADAPTER.parse(body, worldbank_indicator)


def test_row_for_another_indicator_is_a_contract_error(worldbank_indicator: Indicator) -> None:
    with pytest.raises(SourceContractError, match="carries indicator"):
        ADAPTER.parse(payload([row("IRL", "2025", 1.0, ind="OTHER")]), worldbank_indicator)


def test_request_uses_iso3_codes_and_year_range(
    worldbank_indicator: Indicator, countries: CountryCatalogue
) -> None:
    request = ADAPTER.build_request(worldbank_indicator, countries, "2019-01")
    assert request.url == (
        "https://example.test/v2/country/BGR;GRC;IRL;ITA;POL;ROU/indicator/NY.GDP.MKTP.KD.ZG"
    )
    assert ("date", "2019:2026") in request.params
