import json
from typing import Any

import pytest

from asteria.config import CountryCatalogue, Indicator
from asteria.sources.base import SourceContractError
from asteria.sources.eurostat import EurostatAdapter, since_period

ADAPTER = EurostatAdapter("https://example.test/data/")


def jsonstat(dims: dict[str, list[str]], value: Any, status: Any = None) -> bytes:
    doc = {
        "id": list(dims),
        "size": [len(codes) for codes in dims.values()],
        "dimension": {
            d: {"category": {"index": {c: i for i, c in enumerate(codes)}}}
            for d, codes in dims.items()
        },
        "value": value,
        "updated": "2026-09-22T11:00:00+0200",
    }
    if status is not None:
        doc["status"] = status
    return json.dumps(doc).encode()


BASE_DIMS = {"freq": ["M"], "unit": ["PC"], "geo": ["EL", "IE"], "time": ["2025-01", "2025-02"]}


def test_decodes_row_major_index_with_sparse_values_and_status(
    eurostat_indicator: Indicator,
) -> None:
    payload = jsonstat(BASE_DIMS, {"0": 1.5, "1": 1.6, "3": 2.0}, {"1": "p", "2": "c"})
    parsed = ADAPTER.parse(payload, eurostat_indicator)

    got = {(o.geo, o.period): (o.value, o.status) for o in parsed.observations}
    assert got == {
        ("EL", "2025-01"): (1.5, None),
        ("EL", "2025-02"): (1.6, "p"),
        ("IE", "2025-01"): (None, "c"),  # status-only cell: kept, not invented
        ("IE", "2025-02"): (2.0, None),
    }
    assert parsed.source_updated == "2026-09-22T11:00:00+0200"


def test_dense_value_array_is_supported(eurostat_indicator: Indicator) -> None:
    parsed = ADAPTER.parse(jsonstat(BASE_DIMS, [1.0, None, 3.0, 4.0]), eurostat_indicator)
    assert [(o.geo, o.period, o.value) for o in parsed.observations] == [
        ("EL", "2025-01", 1.0),
        ("IE", "2025-01", 3.0),
        ("IE", "2025-02", 4.0),
    ]


def test_unfiltered_dimensions_are_kept_on_each_observation(eurostat_indicator: Indicator) -> None:
    dims = {**BASE_DIMS, "geo": ["EL"], "time": ["2025-01"], "release": ["FIN", "FLS"]}
    parsed = ADAPTER.parse(jsonstat(dims, {"0": 2.1, "1": 2.0}), eurostat_indicator)
    assert [(o.dimensions, o.value) for o in parsed.observations] == [
        ({"release": "FIN"}, 2.1),
        ({"release": "FLS"}, 2.0),
    ]


def test_renamed_filter_dimension_is_a_contract_error(eurostat_indicator: Indicator) -> None:
    """Guards against schema drift such as nace_r2 -> nace_r2_1."""
    dims = {"freq": ["M"], "unit_v2": ["PC"], "geo": ["EL"], "time": ["2025-01"]}
    with pytest.raises(SourceContractError, match="'unit' not in payload"):
        ADAPTER.parse(jsonstat(dims, {"0": 1.0}), eurostat_indicator)


def test_filter_returning_several_codes_is_a_contract_error(eurostat_indicator: Indicator) -> None:
    dims = {**BASE_DIMS, "unit": ["PC", "THS"]}
    with pytest.raises(SourceContractError, match="expected \\['PC'\\]"):
        ADAPTER.parse(jsonstat(dims, {"0": 1.0}), eurostat_indicator)


@pytest.mark.parametrize(
    "payload",
    [b"<html>maintenance</html>", b"[]", json.dumps({"error": [{"label": "bad"}]}).encode()],
)
def test_non_jsonstat_payloads_are_contract_errors(
    payload: bytes, eurostat_indicator: Indicator
) -> None:
    with pytest.raises(SourceContractError):
        ADAPTER.parse(payload, eurostat_indicator)


@pytest.mark.parametrize(
    ("frequency", "expected"), [("M", "2019-04"), ("Q", "2019-Q2"), ("A", "2019")]
)
def test_since_period_matches_frequency_syntax(frequency: str, expected: str) -> None:
    assert since_period("2019-04", frequency) == expected


def test_request_pins_filters_and_repeats_geo(
    eurostat_indicator: Indicator, countries: CountryCatalogue
) -> None:
    request = ADAPTER.build_request(eurostat_indicator, countries, "2019-01")
    assert request.url == "https://example.test/data/demo_ds"
    geos = [v for k, v in request.params if k == "geo"]
    assert sorted(geos) == ["BG", "EL", "IE", "IT", "PL", "RO"]  # Greece is EL at Eurostat
    assert ("unit", "PC") in request.params
    assert ("sinceTimePeriod", "2019-01") in request.params
