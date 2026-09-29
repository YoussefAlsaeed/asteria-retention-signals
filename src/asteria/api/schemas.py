"""Response contracts. The dashboard depends on these shapes, and tests pin them."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

Grain = Literal["month", "quarter", "year"]


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


class Health(BaseModel):
    status: Literal["ok", "data_missing"]
    detail: str | None = None


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


class SignalPoint(BaseModel):
    as_of_date: date
    value: float | None
    signal_frequency: str | None
    signal_period_start: date | None
    signal_period_end: date | None
    signal_age_days: int | None
    signal_status_label: str | None


class SignalSeries(BaseModel):
    country: str
    points: list[SignalPoint]


class AssociationRow(BaseModel):
    indicator_id: str
    model: str
    outcome: str
    n_obs: int
    n_events: int
    n_clusters: int
    signal_sd_within: float | None
    odds_ratio: float | None
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    q_value: float | None
    note: str


class AssociationCell(BaseModel):
    country_code: str
    period_start: date
    n: int
    events: int
    event_rate: float
    signal_mean: float


class FreshnessRow(BaseModel):
    indicator_id: str
    frequency: str
    countries: int
    first_period: date
    last_period: date
    gaps: int
    source_updated: str | None
    loaded_at: str | None
    flagged_values: int
    flag_labels: str | None


class QualityRule(BaseModel):
    rule_id: str
    domain: str
    severity: str
    description: str
    rows_affected: int


class Provider(BaseModel):
    provider_id: str
    name: str
    licence: str
    terms_url: str


class Trust(BaseModel):
    as_of_date: date
    workforce: dict[str, int]
    freshness: list[FreshnessRow]
    quality_rules: list[QualityRule]
    providers: list[Provider]
    definitions: dict[str, str]
