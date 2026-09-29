"""HTTP API over the analytical product, plus the static dashboard.

Error contract (every error is JSON with a `detail` string):
- 404 unknown objective or indicator
- 422 invalid filter value (the message lists the allowed values)
- 503 the analytical product is not built yet (with the command that builds it)
- 500 anything unexpected (logged with a request id; no stack trace is returned)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from asteria import __version__
from asteria.api.repository import DataNotReady, Repository
from asteria.api.schemas import (
    AssociationCell,
    AssociationRow,
    CountryInfo,
    Grain,
    Health,
    MeasureSeries,
    Meta,
    ObjectiveInfo,
    Provider,
    SignalInfo,
    SignalSeries,
    StatusTile,
    Trust,
)
from asteria.context import Context
from asteria.curate.pipeline import DB_FILENAME

log = logging.getLogger(__name__)
BUILD_HINT = "Build it with `uv run asteria run`, then reload."


def create_app(ctx: Context) -> FastAPI:
    app = FastAPI(
        title="Asteria retention signals API",
        version=__version__,
        description="Read-only access to retention objectives and external signals.",
    )
    repo = Repository(ctx.settings.curated_dir / DB_FILENAME)
    objectives = {o.objective_id: o for o in ctx.objectives}
    signals = {s.indicator: s for s in ctx.analysis.signals}
    countries = {c.code: c.name for c in ctx.countries.countries}

    # ------------------------------------------------------------------ plumbing
    @app.exception_handler(DataNotReady)
    async def _not_ready(_: Request, exc: DataNotReady) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": f"{exc}. {BUILD_HINT}"})

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        log.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal error (request id {request_id}). See server logs."},
        )

    @app.middleware("http")
    async def _log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
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
        return response

    def objective_or_404(objective_id: str) -> Any:
        if objective_id not in objectives:
            raise HTTPException(
                404, f"Unknown objective '{objective_id}'. Known: {sorted(objectives)}"
            )
        return objectives[objective_id]

    def signal_or_404(indicator_id: str) -> None:
        if indicator_id not in signals:
            raise HTTPException(404, f"Unknown signal '{indicator_id}'. Known: {sorted(signals)}")

    def check_country(country: str) -> None:
        if country != "ALL" and country not in countries:
            raise HTTPException(422, f"country must be ALL or one of {sorted(countries)}")

    def check_segment(segment: str) -> None:
        if segment != "All" and segment not in repo.segments():
            raise HTTPException(422, f"segment must be All or one of {repo.segments()}")

    # ------------------------------------------------------------------ routes
    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        try:
            missing = repo.missing_tables()
        except DataNotReady as exc:
            return Health(status="data_missing", detail=f"{exc}. {BUILD_HINT}")
        if missing:
            return Health(
                status="data_missing", detail=f"missing tables {sorted(missing)}. {BUILD_HINT}"
            )
        return Health(status="ok")

    @app.get("/api/meta", response_model=Meta)
    def meta() -> Meta:
        variants = repo.variants()
        return Meta(
            as_of_date=ctx.workforce.as_of_date,
            reporting_start=ctx.analysis.reporting_start,
            min_sample=ctx.analysis.min_sample,
            objectives=[
                ObjectiveInfo(
                    objective_id=o.objective_id,
                    name=o.name,
                    measure=o.measure,
                    months=o.months,
                    direction=o.direction,
                    target=o.target,
                    variants=variants.get(o.objective_id, ["main"]),
                )
                for o in ctx.objectives
            ],  # fmt: skip
            countries=[CountryInfo(code=c, name=n) for c, n in countries.items()],
            segment_name=ctx.analysis.segment,
            segments=repo.segments(),
            grains=["month", "quarter", "year"],
            signals=[
                SignalInfo(
                    indicator_id=s.indicator,
                    title=ctx.catalogue.indicator(s.indicator).title,
                    lens=ctx.catalogue.indicator(s.indicator).lens,
                    unit=ctx.catalogue.indicator(s.indicator).unit,
                    frequency=ctx.catalogue.indicator(s.indicator).frequency,
                    provider=ctx.catalogue.providers[
                        ctx.catalogue.indicator(s.indicator).provider
                    ].name,
                    lag_days=s.lag_days,
                )
                for s in ctx.analysis.signals
            ],
        )

    @app.get("/api/objectives/{objective_id}/measures", response_model=MeasureSeries)
    def measures(
        objective_id: str,
        country: str = "ALL",
        segment: str = "All",
        grain: Grain = "quarter",
        variant: str = "main",
    ) -> MeasureSeries:
        spec = objective_or_404(objective_id)
        check_country(country)
        check_segment(segment)
        allowed = repo.variants().get(objective_id, ["main"])
        if variant not in allowed:
            raise HTTPException(422, f"variant for {objective_id} must be one of {allowed}")
        rows = repo.measures(objective_id, country, segment, grain, variant)
        return MeasureSeries(
            objective_id=objective_id, country=country, segment=segment, grain=grain,
            variant=variant, target=spec.target, direction=spec.direction, points=rows,  # type: ignore[arg-type]
        )  # fmt: skip

    @app.get("/api/status", response_model=list[StatusTile])
    def status(country: str = "ALL", segment: str = "All", grain: Grain = "year") -> list[Any]:
        check_country(country)
        check_segment(segment)
        return repo.latest_status(country, segment, grain)

    @app.get("/api/signals/{indicator_id}", response_model=list[SignalSeries])
    def signal(indicator_id: str, country: str = "ALL") -> list[SignalSeries]:
        signal_or_404(indicator_id)
        check_country(country)
        wanted = list(countries) if country == "ALL" else [country]
        rows = repo.signal_series(indicator_id, wanted)
        return [
            SignalSeries(country=code, points=[r for r in rows if r["country_code"] == code])  # type: ignore[misc]
            for code in wanted
        ]

    @app.get("/api/objectives/{objective_id}/associations", response_model=list[AssociationRow])
    def associations(objective_id: str) -> list[Any]:
        objective_or_404(objective_id)
        return repo.associations(objective_id)

    @app.get(
        "/api/objectives/{objective_id}/associations/{indicator_id}/cells",
        response_model=list[AssociationCell],
    )
    def cells(objective_id: str, indicator_id: str) -> list[Any]:
        objective_or_404(objective_id)
        signal_or_404(indicator_id)
        return repo.association_cells(objective_id, indicator_id)

    @app.get("/api/trust", response_model=Trust)
    def trust() -> Trust:
        return Trust(
            as_of_date=ctx.workforce.as_of_date,
            workforce=repo.workforce_counts(),
            freshness=repo.freshness(),  # type: ignore[arg-type]
            quality_rules=repo.quality_rules(),  # type: ignore[arg-type]
            providers=[
                Provider(provider_id=pid, name=p.name, licence=p.licence, terms_url=p.terms_url)
                for pid, p in ctx.catalogue.providers.items()
            ],
            definitions=_definitions(ctx),
        )

    app.mount("/", StaticFiles(directory=ctx.settings.dashboard_dir, html=True), name="dashboard")
    return app


def _definitions(ctx: Context) -> dict[str, str]:
    out = {}
    for o in ctx.objectives:
        if o.measure == "cohort_retention":
            levels = ", ".join(o.levels) if o.levels else "all career levels"
            out[o.objective_id] = (
                f"Share of hires ({levels}) still employed {o.months} calendar months after "
                "their hire date. Hires are grouped by hire month; a period is reported only "
                f"once every hire in it has reached {o.months} months (otherwise 'pending')."
            )
        else:
            out[o.objective_id] = (
                "Regretted exits in the trailing 12 months divided by the mean of the 12 "
                "month-end headcounts in that window. Unknown regretted flags count as not "
                "regretted (an upper-bound variant counts them as regretted)."
            )
    out["signals"] = (
        "Each month uses only values already published by its first day (period end plus "
        "a per-indicator publication lag). Carried-forward values keep their own period "
        "and age; annual figures are never shown as monthly measurements."
    )
    out["associations"] = (
        "Person-level logistic models with country fixed effects, a linear time trend, "
        "and standard errors clustered by country-month; q-values apply the "
        "Benjamini-Hochberg correction across all within-country tests. Association, "
        "not causation."
    )
    out["intervals"] = (
        f"Wilson 95% intervals. 'Insufficient sample' below {ctx.analysis.min_sample} people."
    )
    return out
