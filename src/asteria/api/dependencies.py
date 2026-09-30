"""Injected dependencies: shared state and validated request inputs.

Routes declare what they need (`ObjectiveDep`, `CountryDep`, ...) instead of validating by
hand, so an unknown objective is always a 404 and a bad filter always a 422 that lists the
allowed values.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from asteria.api.repository import Repository
from asteria.config import SignalConfig
from asteria.context import Context
from asteria.domain.objectives import ObjectiveSpec


def get_context(request: Request) -> Context:
    ctx: Context = request.app.state.ctx
    return ctx


def get_repository(request: Request) -> Repository:
    repo: Repository = request.app.state.repository
    return repo


ContextDep = Annotated[Context, Depends(get_context)]
RepositoryDep = Annotated[Repository, Depends(get_repository)]


def country_codes(ctx: Context) -> dict[str, str]:
    """Canonical country code -> name, in configuration order."""
    return {c.code: c.name for c in ctx.countries.countries}


def objective_spec(objective_id: str, ctx: ContextDep) -> ObjectiveSpec:
    for spec in ctx.objectives:
        if spec.objective_id == objective_id:
            return spec
    known = sorted(o.objective_id for o in ctx.objectives)
    raise HTTPException(404, f"Unknown objective '{objective_id}'. Known: {known}")


def signal_config(indicator_id: str, ctx: ContextDep) -> SignalConfig:
    for signal in ctx.analysis.signals:
        if signal.indicator == indicator_id:
            return signal
    known = sorted(s.indicator for s in ctx.analysis.signals)
    raise HTTPException(404, f"Unknown signal '{indicator_id}'. Known: {known}")


def country_filter(ctx: ContextDep, country: str = "ALL") -> str:
    codes = country_codes(ctx)
    if country != "ALL" and country not in codes:
        raise HTTPException(422, f"country must be ALL or one of {sorted(codes)}")
    return country


def segment_filter(repo: RepositoryDep, segment: str = "All") -> str:
    if segment != "All":
        segments = repo.segments()
        if segment not in segments:
            raise HTTPException(422, f"segment must be All or one of {segments}")
    return segment


ObjectiveDep = Annotated[ObjectiveSpec, Depends(objective_spec)]
SignalDep = Annotated[SignalConfig, Depends(signal_config)]
CountryDep = Annotated[str, Depends(country_filter)]
SegmentDep = Annotated[str, Depends(segment_filter)]
