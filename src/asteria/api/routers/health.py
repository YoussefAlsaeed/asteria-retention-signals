from __future__ import annotations

from fastapi import APIRouter

from asteria.api.dependencies import RepositoryDep
from asteria.api.errors import BUILD_HINT
from asteria.api.repository import DataNotReady
from asteria.api.schemas import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
def health(repo: RepositoryDep) -> Health:
    """Is the analytical product built and complete? Never errors: reports instead."""
    try:
        missing = repo.missing_tables()
    except DataNotReady as exc:
        return Health(status="data_missing", detail=f"{exc}. {BUILD_HINT}")
    if missing:
        return Health(
            status="data_missing", detail=f"missing tables {sorted(missing)}. {BUILD_HINT}"
        )
    return Health(status="ok")
