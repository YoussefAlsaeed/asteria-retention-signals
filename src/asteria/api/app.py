"""Application factory: wires state, error handling, middleware, routers and the dashboard.

The pieces live in their own modules:
- `routers/`       one module per resource (health, meta, objectives, signals, ...)
- `dependencies`   injected context/repository and validated inputs (404 / 422)
- `repository/`    every SQL query, grouped by domain, read-only
- `schemas/`       response contracts
- `services/`      response-building logic that is neither HTTP nor SQL
- `errors`         the error contract (503 not built, 500 with request id)
- `middleware`     request id, logging, cache headers
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from asteria import __version__
from asteria.api.errors import register_error_handlers
from asteria.api.middleware import register_middleware
from asteria.api.repository import Repository
from asteria.api.routers import ROUTERS
from asteria.context import Context
from asteria.curate.pipeline import DB_FILENAME


def create_app(ctx: Context) -> FastAPI:
    app = FastAPI(
        title="Asteria retention signals API",
        version=__version__,
        description="Read-only access to retention objectives and external signals.",
    )
    app.state.ctx = ctx
    app.state.repository = Repository(ctx.settings.curated_dir / DB_FILENAME)

    register_error_handlers(app)
    register_middleware(app)
    for router in ROUTERS:
        app.include_router(router)

    # Mounted last so /api/* and /docs take precedence over static files.
    app.mount("/", StaticFiles(directory=ctx.settings.dashboard_dir, html=True), name="dashboard")
    return app
