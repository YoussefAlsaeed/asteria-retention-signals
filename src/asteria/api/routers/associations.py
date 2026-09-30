from __future__ import annotations

from fastapi import APIRouter

from asteria.api.dependencies import ObjectiveDep, RepositoryDep, SignalDep
from asteria.api.schemas import AssociationCell, AssociationRow

router = APIRouter(prefix="/api", tags=["associations"])


@router.get("/objectives/{objective_id}/associations", response_model=list[AssociationRow])
def associations(spec: ObjectiveDep, repo: RepositoryDep) -> list[AssociationRow]:
    """Naive and within-country model results for one objective, per signal."""
    return [AssociationRow(**row) for row in repo.associations(spec.objective_id)]


@router.get(
    "/objectives/{objective_id}/associations/{indicator_id}/cells",
    response_model=list[AssociationCell],
)
def cells(spec: ObjectiveDep, signal: SignalDep, repo: RepositoryDep) -> list[AssociationCell]:
    """Country-quarter points behind the relationship scatter."""
    rows = repo.association_cells(spec.objective_id, signal.indicator)
    return [AssociationCell(**row) for row in rows]
