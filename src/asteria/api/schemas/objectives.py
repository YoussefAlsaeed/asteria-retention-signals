"""Objective measures: time series per slice, and the latest status per objective."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from asteria.api.schemas.meta import Grain


class MeasurePoint(BaseModel):
    period_start: date
    period_end: date
    numerator: float
    denominator: float
    rate: float | None
    ci_low: float | None
    ci_high: float | None
    status: str
    confidence: str | None


class MeasureSeries(BaseModel):
    objective_id: str
    country: str
    segment: str
    grain: Grain
    variant: str
    target: float
    direction: str
    points: list[MeasurePoint]


class StatusTile(MeasurePoint):
    objective_id: str
    target: float
    direction: str
    pending_periods: int
