from __future__ import annotations

from fastapi import APIRouter

from asteria.api.dependencies import ContextDep, RepositoryDep
from asteria.api.schemas import Meta
from asteria.api.services.meta import build_meta

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=Meta)
def meta(ctx: ContextDep, repo: RepositoryDep) -> Meta:
    """Objectives, countries, segments, grains and signals: everything the filters need."""
    return build_meta(ctx, repo)
