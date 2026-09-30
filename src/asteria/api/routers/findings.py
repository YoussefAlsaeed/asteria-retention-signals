from __future__ import annotations

from fastapi import APIRouter

from asteria.api.dependencies import ContextDep, RepositoryDep
from asteria.api.schemas import Findings
from asteria.api.services.findings import build_findings

router = APIRouter(prefix="/api", tags=["findings"])


@router.get("/findings", response_model=Findings)
def findings(ctx: ContextDep, repo: RepositoryDep) -> Findings:
    """The headline numbers behind docs/findings.md, computed live."""
    return build_findings(repo, (o.objective_id for o in ctx.objectives))
