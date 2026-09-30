"""Service metadata: health and the filter options the dashboard is built from."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

Grain = Literal["month", "quarter", "year"]


class Health(BaseModel):
    status: Literal["ok", "data_missing"]
    detail: str | None = None


class ObjectiveInfo(BaseModel):
    objective_id: str
    name: str
    measure: str
    months: int
    direction: str
    target: float
    variants: list[str]


class SignalInfo(BaseModel):
    indicator_id: str
    title: str
    lens: str
    unit: str
    frequency: str
    provider: str
    lag_days: int


class CountryInfo(BaseModel):
    code: str
    name: str


class Meta(BaseModel):
    as_of_date: date
    reporting_start: str
    min_sample: int
    objectives: list[ObjectiveInfo]
    countries: list[CountryInfo]
    segment_name: str
    segments: list[str]
    grains: list[Grain]
    signals: list[SignalInfo]
