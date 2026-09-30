from __future__ import annotations

from fastapi import APIRouter

from asteria.api.dependencies import ContextDep, RepositoryDep
from asteria.api.schemas import FreshnessRow, Provider, QualityRule, Trust
from asteria.api.services.definitions import method_definitions

router = APIRouter(prefix="/api", tags=["trust"])


@router.get("/trust", response_model=Trust)
def trust(ctx: ContextDep, repo: RepositoryDep) -> Trust:
    """Freshness, coverage, quality rules, sources and method definitions."""
    return Trust(
        as_of_date=ctx.workforce.as_of_date,
        workforce=repo.workforce_counts(),
        freshness=[FreshnessRow(**row) for row in repo.freshness()],
        quality_rules=[QualityRule(**row) for row in repo.quality_rules()],
        providers=[
            Provider(provider_id=pid, name=p.name, licence=p.licence, terms_url=p.terms_url)
            for pid, p in ctx.catalogue.providers.items()
        ],
        definitions=method_definitions(ctx),
    )
