"""Eurostat dissemination API adapter (JSON-stat 2.0).

API guide: https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/api
"""

from __future__ import annotations

import json
from typing import Any

from asteria.config import CountryCatalogue, Indicator
from asteria.sources.base import (
    ParsedPayload,
    SourceContractError,
    SourceObservation,
    SourceRequest,
)

GEO, TIME = "geo", "time"


def since_period(history_start: str, frequency: str) -> str:
    """Express a YYYY-MM start in the period syntax Eurostat uses for the frequency."""
    year, month = history_start.split("-")
    if frequency == "M":
        return f"{year}-{month}"
    if frequency == "Q":
        return f"{year}-Q{(int(month) - 1) // 3 + 1}"
    return year


class EurostatAdapter:
    provider_id = "eurostat"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def expected_geos(self, countries: CountryCatalogue) -> set[str]:
        return {c.eurostat for c in countries.countries}

    def build_request(
        self, indicator: Indicator, countries: CountryCatalogue, history_start: str
    ) -> SourceRequest:
        params = [("format", "JSON"), ("lang", "EN")]
        params += sorted(indicator.filters.items())
        params += [(GEO, geo) for geo in sorted(self.expected_geos(countries))]
        params.append(("sinceTimePeriod", since_period(history_start, indicator.frequency)))
        return SourceRequest(url=f"{self.base_url}/{indicator.dataset}", params=params)

    def parse(self, payload: bytes, indicator: Indicator) -> ParsedPayload:
        try:
            doc = json.loads(payload)
        except ValueError as exc:
            raise SourceContractError(f"{indicator.dataset}: payload is not JSON") from exc
        if not isinstance(doc, dict):
            raise SourceContractError(f"{indicator.dataset}: expected a JSON-stat object")
        if "error" in doc:
            raise SourceContractError(f"{indicator.dataset}: provider error {doc['error']}")

        ids, sizes, categories = _read_structure(doc, indicator)
        _check_filters(categories, indicator)

        values = _as_sparse(doc.get("value", {}))
        statuses = _as_sparse(doc.get("status", {}))
        extra_dims = [d for d in ids if d not in indicator.filters and d not in (GEO, TIME)]

        observations = []
        for flat in sorted(values.keys() | statuses.keys()):
            coords = _unflatten(flat, sizes)
            codes = {dim: categories[dim][pos] for dim, pos in zip(ids, coords, strict=True)}
            value = values.get(flat)
            observations.append(
                SourceObservation(
                    indicator_id=indicator.id,
                    geo=codes[GEO],
                    period=codes[TIME],
                    value=None if value is None else float(value),
                    status=statuses.get(flat),
                    dimensions={d: codes[d] for d in extra_dims},
                )
            )
        return ParsedPayload(observations=observations, source_updated=doc.get("updated"))


def _read_structure(
    doc: dict[str, Any], indicator: Indicator
) -> tuple[list[str], list[int], dict[str, list[str]]]:
    try:
        ids: list[str] = list(doc["id"])
        sizes: list[int] = [int(s) for s in doc["size"]]
        dimension = doc["dimension"]
        categories = {}
        for dim in ids:
            index: dict[str, int] = dimension[dim]["category"]["index"]
            categories[dim] = [code for code, _ in sorted(index.items(), key=lambda kv: kv[1])]
    except (KeyError, TypeError) as exc:
        raise SourceContractError(
            f"{indicator.dataset}: JSON-stat structure incomplete ({exc!r})"
        ) from exc
    if len(ids) != len(sizes) or any(
        len(categories[d]) != s for d, s in zip(ids, sizes, strict=False)
    ):
        raise SourceContractError(f"{indicator.dataset}: dimension sizes do not match categories")
    for required in (GEO, TIME):
        if required not in ids:
            raise SourceContractError(f"{indicator.dataset}: missing '{required}' dimension")
    return ids, sizes, categories


def _check_filters(categories: dict[str, list[str]], indicator: Indicator) -> None:
    """Every filtered dimension must come back pinned to exactly the requested code."""
    for dim, wanted in indicator.filters.items():
        if dim not in categories:
            raise SourceContractError(
                f"{indicator.dataset}: filter dimension '{dim}' not in payload "
                f"(dimensions: {sorted(categories)}); the dataset schema may have changed"
            )
        if categories[dim] != [wanted]:
            raise SourceContractError(
                f"{indicator.dataset}: dimension '{dim}' returned {categories[dim]}, "
                f"expected ['{wanted}']"
            )


def _as_sparse(raw: Any) -> dict[int, Any]:
    """JSON-stat allows values as a dense array or a sparse {index: value} object."""
    if isinstance(raw, list):
        return {i: v for i, v in enumerate(raw) if v is not None}
    return {int(k): v for k, v in raw.items()}


def _unflatten(flat: int, sizes: list[int]) -> list[int]:
    """Row-major flat index to per-dimension positions (last dimension varies fastest)."""
    coords = []
    for size in reversed(sizes):
        flat, position = divmod(flat, size)
        coords.append(position)
    return coords[::-1]
