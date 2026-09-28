"""World Bank Indicators API (v2) adapter.

API guide: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation
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

# Six countries x a few decades fits one page; the parser rejects multi-page payloads
# rather than silently dropping pages.
PER_PAGE = 1000


class WorldBankAdapter:
    provider_id = "worldbank"

    def __init__(self, base_url: str, end_year: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.end_year = end_year

    def expected_geos(self, countries: CountryCatalogue) -> set[str]:
        return {c.worldbank for c in countries.countries}

    def build_request(
        self, indicator: Indicator, countries: CountryCatalogue, history_start: str
    ) -> SourceRequest:
        geos = ";".join(sorted(self.expected_geos(countries)))
        start_year = history_start.split("-")[0]
        return SourceRequest(
            url=f"{self.base_url}/country/{geos}/indicator/{indicator.dataset}",
            params=[
                ("format", "json"),
                ("date", f"{start_year}:{self.end_year}"),
                ("per_page", str(PER_PAGE)),
            ],
        )

    def parse(self, payload: bytes, indicator: Indicator) -> ParsedPayload:
        try:
            doc = json.loads(payload)
        except ValueError as exc:
            raise SourceContractError(f"{indicator.dataset}: payload is not JSON") from exc

        # Errors arrive as HTTP 200 with a single-element list: [{"message": [...]}].
        if isinstance(doc, list) and len(doc) == 1 and isinstance(doc[0], dict):
            messages = doc[0].get("message", doc[0])
            raise SourceContractError(f"{indicator.dataset}: provider error {messages}")
        if not (isinstance(doc, list) and len(doc) == 2 and isinstance(doc[0], dict)):
            raise SourceContractError(f"{indicator.dataset}: expected [metadata, rows]")

        meta: dict[str, Any] = doc[0]
        if int(meta.get("pages", 1)) > 1:
            raise SourceContractError(
                f"{indicator.dataset}: {meta['pages']} pages returned; "
                f"raise PER_PAGE above {PER_PAGE} so no page is dropped"
            )

        observations = []
        for row in doc[1] or []:
            try:
                geo, period, value = row["countryiso3code"], row["date"], row["value"]
            except (KeyError, TypeError) as exc:
                raise SourceContractError(f"{indicator.dataset}: malformed row {row!r}") from exc
            if row.get("indicator", {}).get("id") != indicator.dataset:
                raise SourceContractError(
                    f"{indicator.dataset}: row carries indicator {row.get('indicator')}"
                )
            observations.append(
                SourceObservation(
                    indicator_id=indicator.id,
                    geo=geo,
                    period=str(period),
                    value=None if value is None else float(value),
                    status=row.get("obs_status") or None,
                )
            )
        return ParsedPayload(observations=observations, source_updated=meta.get("lastupdated"))
