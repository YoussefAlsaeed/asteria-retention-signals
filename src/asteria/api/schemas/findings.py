"""Headline numbers behind docs/findings.md, computed live from the analytical product."""

from __future__ import annotations

from pydantic import BaseModel

from asteria.api.schemas.signals import AssociationRow


class PooledCohort(BaseModel):
    objective_id: str
    variant: str
    numerator: float
    denominator: float
    rate: float
    ci_low: float
    ci_high: float
    first_year: int
    last_year: int
    yearly_rates: list[float]


class TurnoverYear(BaseModel):
    year: int
    numerator: float
    denominator: float
    rate: float | None
    ci_low: float | None
    ci_high: float | None
    status: str
    confidence: str | None


class Findings(BaseModel):
    pooled: list[PooledCohort]
    turnover: list[TurnoverYear]
    association_tests: int
    association_significant: int
    smallest_q: float | None
    strongest: AssociationRow | None
    strongest_objective: str | None
