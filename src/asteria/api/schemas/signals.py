"""Point-in-time signal series and association results."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


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
