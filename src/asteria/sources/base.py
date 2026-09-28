"""Adapter contract shared by every external provider.

An adapter knows one provider's wire format: how to build a request for an indicator and
how to turn the raw payload into source-shaped observations. It performs no I/O, so it is
unit-testable against fixtures, and the ingest layer owns retries, storage, and logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from asteria.config import CountryCatalogue, Indicator


class SourceError(Exception):
    """Base class for failures retrieving or interpreting a source."""


class TransientSourceError(SourceError):
    """Temporary failure (timeout, 5xx, rate limit). Safe to retry."""


class SourceRequestError(SourceError):
    """The provider rejected the request (4xx). Retrying will not help."""


class SourceContractError(SourceError):
    """The payload does not match the shape this adapter expects."""


@dataclass(frozen=True)
class SourceRequest:
    url: str
    # A list, not a dict: Eurostat expects repeated keys such as geo=EL&geo=RO.
    params: list[tuple[str, str]]


@dataclass(frozen=True)
class SourceObservation:
    """One value exactly as the provider reports it (provider codes, provider periods)."""

    indicator_id: str
    geo: str
    period: str
    value: float | None
    status: str | None
    dimensions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedPayload:
    observations: list[SourceObservation]
    source_updated: str | None


class SourceAdapter(Protocol):
    provider_id: str

    def build_request(
        self, indicator: Indicator, countries: CountryCatalogue, history_start: str
    ) -> SourceRequest: ...

    def expected_geos(self, countries: CountryCatalogue) -> set[str]: ...

    def parse(self, payload: bytes, indicator: Indicator) -> ParsedPayload: ...
