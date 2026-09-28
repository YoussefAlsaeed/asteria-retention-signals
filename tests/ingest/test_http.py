import json
from collections.abc import Callable

import httpx
import pytest
from tenacity import wait_none

from asteria.ingest.http import HttpFetcher
from asteria.sources.base import SourceRequest, SourceRequestError, TransientSourceError

REQUEST = SourceRequest("https://example.test/data/x", [("geo", "EL"), ("geo", "IE")])


def fetcher_with(responses: list[httpx.Response | Exception]) -> tuple[HttpFetcher, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpFetcher(client, max_attempts=3, wait=wait_none()), calls


def test_transient_failure_is_retried_then_succeeds() -> None:
    fetcher, calls = fetcher_with([httpx.Response(503), httpx.Response(200, content=b"{}")])
    result = fetcher.get(REQUEST)
    assert result.content == b"{}"
    assert result.attempts == 2
    assert len(calls) == 2


def test_repeated_query_keys_are_sent() -> None:
    fetcher, calls = fetcher_with([httpx.Response(200, content=b"{}")])
    fetcher.get(REQUEST)
    assert calls[0].endswith("?geo=EL&geo=IE")


def test_client_error_fails_fast_with_provider_message() -> None:
    body = {"error": [{"status": 400, "label": "Dimension 'nace_r2' does not exist"}]}
    fetcher, calls = fetcher_with([httpx.Response(400, content=json.dumps(body).encode())])
    with pytest.raises(SourceRequestError, match="nace_r2' does not exist"):
        fetcher.get(REQUEST)
    assert len(calls) == 1  # no retry on a 4xx


@pytest.mark.parametrize(
    "failure",
    [
        lambda: httpx.ReadTimeout("slow"),
        lambda: httpx.ConnectError("dns"),
        lambda: httpx.Response(429),
    ],
    ids=["timeout", "connect", "rate-limit"],
)
def test_transient_failures_give_up_after_max_attempts(
    failure: Callable[[], httpx.Response | Exception],
) -> None:
    fetcher, calls = fetcher_with([failure()])
    with pytest.raises(TransientSourceError):
        fetcher.get(REQUEST)
    assert len(calls) == 3
