"""Ingest orchestration: fetch or replay each indicator, validate, store, and report.

Each indicator is isolated. One failing source is recorded and the run continues; its
previous snapshot is kept, so a partial failure never corrupts good evidence.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from asteria.config import CountryCatalogue, Indicator, Mode, SourceCatalogue
from asteria.ingest.http import HttpFetcher
from asteria.ingest.raw_store import RawStore, SnapshotMeta, sha256_hex
from asteria.sources.base import ParsedPayload, SourceAdapter, SourceError

log = logging.getLogger(__name__)


@dataclass
class GeoCoverage:
    observations: int
    first_period: str | None
    last_period: str | None


@dataclass
class IndicatorOutcome:
    indicator_id: str
    provider: str
    dataset: str
    status: str  # "ok" | "failed"
    change: str | None = None  # created | updated | unchanged | replayed
    observations: int = 0
    source_updated: str | None = None
    sha256: str | None = None
    attempts: int | None = None
    coverage: dict[str, GeoCoverage] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error_type: str | None = None
    error: str | None = None


@dataclass
class IngestReport:
    run_id: str
    mode: Mode
    started_at: str
    finished_at: str
    outcomes: list[IndicatorOutcome]

    @property
    def failed(self) -> list[IndicatorOutcome]:
        return [o for o in self.outcomes if o.status == "failed"]


def run_ingest(
    catalogue: SourceCatalogue,
    countries: CountryCatalogue,
    adapters: dict[str, SourceAdapter],
    store: RawStore,
    mode: Mode,
    fetcher: HttpFetcher | None = None,
    only: list[str] | None = None,
) -> IngestReport:
    if mode == "live" and fetcher is None:
        raise ValueError("live mode needs an HttpFetcher")
    indicators = [catalogue.indicator(i) for i in only] if only else catalogue.indicators
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    started = _now()
    log.info(
        "ingest started", extra={"run_id": run_id, "mode": mode, "indicators": len(indicators)}
    )

    outcomes = []
    for indicator in indicators:
        adapter = adapters[indicator.provider]
        outcome = IndicatorOutcome(indicator.id, indicator.provider, indicator.dataset, "ok")
        try:
            if mode == "live":
                assert fetcher is not None
                parsed = _ingest_live(
                    indicator, adapter, countries, catalogue, store, fetcher, outcome
                )
            else:
                parsed = _ingest_replay(indicator, adapter, store, outcome)
            _summarise(parsed, adapter.expected_geos(countries), outcome)
        except SourceError as exc:
            _fail(outcome, exc)
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the others
            log.exception("unexpected ingest error", extra={"indicator": indicator.id})
            _fail(outcome, exc)
        log.info(
            "indicator ingested" if outcome.status == "ok" else "indicator failed",
            extra={"run_id": run_id, **_log_fields(outcome)},
        )
        outcomes.append(outcome)

    return IngestReport(run_id, mode, started, _now(), outcomes)


def _ingest_live(
    indicator: Indicator,
    adapter: SourceAdapter,
    countries: CountryCatalogue,
    catalogue: SourceCatalogue,
    store: RawStore,
    fetcher: HttpFetcher,
    outcome: IndicatorOutcome,
) -> ParsedPayload:
    request = adapter.build_request(indicator, countries, catalogue.history_start)
    result = fetcher.get(request)
    outcome.attempts = result.attempts
    # Validate before storing: a payload that breaks the contract never replaces good evidence.
    parsed = adapter.parse(result.content, indicator)
    meta = SnapshotMeta(
        provider=indicator.provider,
        indicator_id=indicator.id,
        dataset=indicator.dataset,
        request_url=request.url,
        request_params=request.params,
        fetched_at=_now(),
        http_status=result.status_code,
        sha256=sha256_hex(result.content),
        bytes=len(result.content),
        source_updated=parsed.source_updated,
        observation_count=len(parsed.observations),
    )
    outcome.change = store.write(result.content, meta)
    outcome.sha256 = meta.sha256
    return parsed


def _ingest_replay(
    indicator: Indicator, adapter: SourceAdapter, store: RawStore, outcome: IndicatorOutcome
) -> ParsedPayload:
    content, meta = store.read(indicator.provider, indicator.id)
    outcome.change = "replayed"
    outcome.sha256 = meta.sha256
    return adapter.parse(content, indicator)


def _summarise(parsed: ParsedPayload, expected: set[str], outcome: IndicatorOutcome) -> None:
    outcome.observations = len(parsed.observations)
    outcome.source_updated = parsed.source_updated
    periods: dict[str, list[str]] = defaultdict(list)
    for obs in parsed.observations:
        if obs.value is not None:
            periods[obs.geo].append(obs.period)
    outcome.coverage = {
        geo: GeoCoverage(len(p), min(p), max(p)) for geo, p in sorted(periods.items())
    }
    missing = sorted(expected - periods.keys())
    if missing:
        outcome.warnings.append(f"no values for: {missing}")
    unexpected = sorted(periods.keys() - expected)
    if unexpected:
        outcome.warnings.append(f"unrequested geos returned: {unexpected}")
    empty = sum(1 for o in parsed.observations if o.value is None)
    if empty:
        outcome.warnings.append(f"{empty} observations carry a status but no value")


def _fail(outcome: IndicatorOutcome, exc: Exception) -> None:
    outcome.status = "failed"
    outcome.error_type = type(exc).__name__
    outcome.error = str(exc)


def write_run_manifest(report: IngestReport, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"ingest_{report.run_id}.json"
    path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    return path


def _log_fields(outcome: IndicatorOutcome) -> dict[str, object]:
    fields: dict[str, object] = {
        "indicator": outcome.indicator_id,
        "status": outcome.status,
        "change": outcome.change,
        "observations": outcome.observations,
        "attempts": outcome.attempts,
    }
    if outcome.error:
        fields |= {"error_type": outcome.error_type, "error": outcome.error}
    return fields


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
