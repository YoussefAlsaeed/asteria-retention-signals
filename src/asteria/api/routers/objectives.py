from __future__ import annotations

from fastapi import APIRouter, HTTPException

from asteria.api.dependencies import CountryDep, ObjectiveDep, RepositoryDep, SegmentDep
from asteria.api.schemas import Grain, MeasurePoint, MeasureSeries, StatusTile

router = APIRouter(prefix="/api", tags=["objectives"])


@router.get("/objectives/{objective_id}/measures", response_model=MeasureSeries)
def measures(
    spec: ObjectiveDep,
    repo: RepositoryDep,
    country: CountryDep,
    segment: SegmentDep,
    grain: Grain = "quarter",
    variant: str = "main",
) -> MeasureSeries:
    """One objective over time for one country x segment slice."""
    allowed = repo.variants().get(spec.objective_id, ["main"])
    if variant not in allowed:
        raise HTTPException(422, f"variant for {spec.objective_id} must be one of {allowed}")
    rows = repo.measures(spec.objective_id, country, segment, grain, variant)
    return MeasureSeries(
        objective_id=spec.objective_id,
        country=country,
        segment=segment,
        grain=grain,
        variant=variant,
        target=spec.target,
        direction=spec.direction,
        points=[MeasurePoint(**row) for row in rows],
    )


@router.get("/status", response_model=list[StatusTile])
def status(
    repo: RepositoryDep, country: CountryDep, segment: SegmentDep, grain: Grain = "year"
) -> list[StatusTile]:
    """Latest measurable period per objective (main definition)."""
    return [StatusTile(**row) for row in repo.latest_status(country, segment, grain)]
