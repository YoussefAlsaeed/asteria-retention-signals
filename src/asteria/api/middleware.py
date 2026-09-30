"""Request id, request logging, and cache headers."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

log = logging.getLogger(__name__)


async def _observe(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        # Data changes on every rebuild: never cache API responses.
        response.headers["Cache-Control"] = "no-store"
        log.info(
            "request",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
    else:
        # Dashboard files: browsers must revalidate (cheap 304 via ETag), so an updated
        # dashboard is never served from a stale cache.
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


def register_middleware(app: FastAPI) -> None:
    app.middleware("http")(_observe)
