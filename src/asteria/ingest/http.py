"""HTTP retrieval with timeouts, bounded retries, and a small error taxonomy.

Only transient failures (timeouts, connection errors, 429, 5xx) are retried. A 4xx means
the request itself is wrong, so it fails immediately with the provider's own message.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tenacity.wait import wait_base

from asteria import __version__
from asteria.sources.base import SourceRequest, SourceRequestError, TransientSourceError

log = logging.getLogger(__name__)

TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
USER_AGENT = f"asteria-retention-signals/{__version__}"


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    status_code: int
    url: str
    attempts: int
    elapsed_seconds: float


class HttpFetcher:
    def __init__(
        self,
        client: httpx.Client,
        max_attempts: int = 4,
        wait: wait_base | None = None,
    ) -> None:
        self.client = client
        self.max_attempts = max_attempts
        self.wait = wait or wait_exponential_jitter(initial=1, max=20)

    @classmethod
    def create(cls, timeout_seconds: float, max_attempts: int) -> HttpFetcher:
        client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        return cls(client, max_attempts)

    def close(self) -> None:
        self.client.close()

    def get(self, request: SourceRequest) -> FetchResult:
        started = time.monotonic()
        retrying = Retrying(
            retry=retry_if_exception_type(TransientSourceError),
            stop=stop_after_attempt(self.max_attempts),
            wait=self.wait,
            before_sleep=_log_retry,
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                response = self._send(request)
        return FetchResult(
            content=response.content,
            status_code=response.status_code,
            url=str(response.url),
            attempts=retrying.statistics.get("attempt_number", 1),
            elapsed_seconds=round(time.monotonic() - started, 3),
        )

    def _send(self, request: SourceRequest) -> httpx.Response:
        # Re-typed for httpx's wider value type (list is invariant under mypy).
        params: list[tuple[str, str | int | float | bool | None]] = list(request.params)
        try:
            response = self.client.get(request.url, params=params)
        except httpx.TimeoutException as exc:
            raise TransientSourceError(f"timeout calling {request.url}") from exc
        except httpx.TransportError as exc:
            raise TransientSourceError(
                f"connection failed for {request.url}: {type(exc).__name__}"
            ) from exc

        if response.status_code in TRANSIENT_STATUS:
            raise TransientSourceError(
                f"HTTP {response.status_code} from {request.url}: {_provider_message(response)}"
            )
        if response.status_code >= 400:
            raise SourceRequestError(
                f"HTTP {response.status_code} from {request.url}: {_provider_message(response)}"
            )
        return response


def _provider_message(response: httpx.Response) -> str:
    """Surface the provider's own error text (Eurostat puts it in error[0].label)."""
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        return response.text[:200].strip() or "<empty body>"
    if isinstance(body, dict) and isinstance(body.get("error"), list) and body["error"]:
        first = body["error"][0]
        if isinstance(first, dict) and "label" in first:
            return str(first["label"])
    return json.dumps(body)[:200]


def _log_retry(state: RetryCallState) -> None:
    error = state.outcome.exception() if state.outcome else None
    log.warning(
        "retrying request",
        extra={
            "attempt": state.attempt_number,
            "next_wait_seconds": round(state.next_action.sleep, 2) if state.next_action else None,
            "error": str(error),
        },
    )
