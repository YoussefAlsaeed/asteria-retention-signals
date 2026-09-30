"""The Data trust view: freshness, quality rules, sources, and method definitions."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


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
