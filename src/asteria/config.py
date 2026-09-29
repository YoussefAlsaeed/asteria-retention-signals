"""Typed, validated configuration loaded from config/*.yaml.

Invalid configuration fails at load time with the file and field named, never mid-run.
"""

from __future__ import annotations

from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

Frequency = Literal["M", "Q", "A"]
Lens = Literal["labour_supply", "labour_demand", "cost_of_living", "economic_cycle"]
Mode = Literal["live", "replay"]
M = TypeVar("M", bound=BaseModel)


class ConfigError(Exception):
    """Configuration is missing or invalid."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Provider(_Frozen):
    name: str
    base_url: str
    licence: str
    terms_url: str


class Indicator(_Frozen):
    id: str
    provider: str
    dataset: str
    lens: Lens
    title: str
    frequency: Frequency
    unit: str
    filters: dict[str, str]


class Country(_Frozen):
    code: str
    name: str
    eurostat: str
    worldbank: str
    aliases: list[str]


class SourceCatalogue(_Frozen):
    providers: dict[str, Provider]
    history_start: str
    indicators: list[Indicator]

    @model_validator(mode="after")
    def _check_references(self) -> SourceCatalogue:
        ids = [i.id for i in self.indicators]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate indicator ids: {duplicates}")
        unknown = sorted({i.provider for i in self.indicators} - self.providers.keys())
        if unknown:
            raise ValueError(f"indicators reference unknown providers: {unknown}")
        return self

    def indicator(self, indicator_id: str) -> Indicator:
        for indicator in self.indicators:
            if indicator.id == indicator_id:
                return indicator
        raise ConfigError(
            f"unknown indicator '{indicator_id}'; known: {[i.id for i in self.indicators]}"
        )


class CountryCatalogue(_Frozen):
    countries: list[Country]

    @cached_property
    def by_alias(self) -> dict[str, str]:
        """Every accepted code (canonical or alias) mapped to its canonical code."""
        mapping = {c.code: c.code for c in self.countries}
        for country in self.countries:
            mapping.update({alias: country.code for alias in country.aliases})
        return mapping


class WorkforceAllowed(_Frozen):
    business_unit: list[str]
    career_level: list[str]
    employment_type: list[str]
    termination_type: list[str]
    source_system: list[str]


class WorkforceConfig(_Frozen):
    source_file: Path
    as_of_date: date
    allowed: WorkforceAllowed
    career_level_aliases: dict[str, str]

    @model_validator(mode="after")
    def _aliases_point_to_allowed_levels(self) -> WorkforceConfig:
        bad = sorted(set(self.career_level_aliases.values()) - set(self.allowed.career_level))
        if bad:
            raise ValueError(f"career_level_aliases map to levels not in allowed: {bad}")
        return self

    def source_path(self, root: Path = ROOT) -> Path:
        return self.source_file if self.source_file.is_absolute() else root / self.source_file


class ObjectiveRuleConfig(_Frozen):
    measure: Literal["cohort_retention", "trailing_regretted_turnover"]
    months: int
    levels: list[str] | None = None
    sensitivity_levels: list[str] | None = None


class SignalConfig(_Frozen):
    indicator: str
    lag_days: int
    release: str | None = None


class AnalysisConfig(_Frozen):
    objectives_file: Path
    reporting_start: str
    min_sample: int
    objectives: dict[str, ObjectiveRuleConfig]
    segment: Literal["business_unit", "employment_type", "career_level", "job_family"]
    signals: list[SignalConfig]

    @model_validator(mode="after")
    def _check(self) -> AnalysisConfig:
        ids = [s.indicator for s in self.signals]
        if len(ids) != len(set(ids)):
            raise ValueError("each signal indicator may appear once")
        if any(s.lag_days < 0 for s in self.signals):
            raise ValueError("lag_days cannot be negative")
        return self

    def objectives_path(self, root: Path = ROOT) -> Path:
        path = self.objectives_file
        return path if path.is_absolute() else root / path


class Settings(BaseSettings):
    """Runtime settings; override with ASTERIA_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="ASTERIA_")

    config_dir: Path = ROOT / "config"
    data_dir: Path = ROOT / "data"
    mode: Mode = "replay"
    http_timeout_seconds: float = 60.0
    http_max_attempts: int = 4

    @property
    def raw_sources_dir(self) -> Path:
        return self.data_dir / "raw-or-fixtures" / "sources"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def curated_dir(self) -> Path:
        return self.data_dir / "curated"

    dashboard_dir: Path = ROOT / "dashboard"


def _load_model(config_dir: Path, filename: str, model: type[M]) -> M:
    path = config_dir / filename
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file is not valid YAML: {path}: {exc}") from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid {filename}:\n{exc}") from exc


def load_sources(config_dir: Path) -> SourceCatalogue:
    return _load_model(config_dir, "sources.yaml", SourceCatalogue)


def load_countries(config_dir: Path) -> CountryCatalogue:
    return _load_model(config_dir, "countries.yaml", CountryCatalogue)


def load_workforce(config_dir: Path) -> WorkforceConfig:
    return _load_model(config_dir, "workforce.yaml", WorkforceConfig)


def load_analysis(config_dir: Path, catalogue: SourceCatalogue) -> AnalysisConfig:
    config = _load_model(config_dir, "analysis.yaml", AnalysisConfig)
    for signal in config.signals:
        catalogue.indicator(signal.indicator)  # unknown indicator -> ConfigError
    return config
