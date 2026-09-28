"""Typed, validated configuration loaded from config/*.yaml.

Invalid configuration fails at load time with the file and field named, never mid-run.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

Frequency = Literal["M", "Q", "A"]
Lens = Literal["labour_supply", "labour_demand", "cost_of_living", "economic_cycle"]
Mode = Literal["live", "replay"]


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


def _load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file is not valid YAML: {path}: {exc}") from exc


def load_sources(config_dir: Path) -> SourceCatalogue:
    path = config_dir / "sources.yaml"
    try:
        return SourceCatalogue.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"invalid {path.name}:\n{exc}") from exc


def load_countries(config_dir: Path) -> CountryCatalogue:
    path = config_dir / "countries.yaml"
    try:
        return CountryCatalogue.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"invalid {path.name}:\n{exc}") from exc
