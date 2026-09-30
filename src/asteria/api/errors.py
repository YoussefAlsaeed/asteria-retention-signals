"""The API error contract. Every error is JSON with a `detail` string:

- 404 unknown objective or indicator (raised by `dependencies`)
- 422 invalid filter value; the message lists the allowed values
- 503 the analytical product is not built yet, with the command that builds it
- 500 anything unexpected: logged with a request id; no stack trace is returned
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from asteria.api.repository import DataNotReady

log = logging.getLogger(__name__)
BUILD_HINT = "Build it with `uv run asteria run`, then reload."


async def _not_ready(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": f"{exc}. {BUILD_HINT}"})


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "-")
    log.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error (request id {request_id}). See server logs."},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DataNotReady, _not_ready)
    app.add_exception_handler(Exception, _unexpected)
