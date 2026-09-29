"""Everything a command or the API needs, loaded and validated once from config/."""

from __future__ import annotations

from dataclasses import dataclass

from asteria.config import (
    AnalysisConfig,
    ConfigError,
    CountryCatalogue,
    Settings,
    SourceCatalogue,
    WorkforceConfig,
    load_analysis,
    load_countries,
    load_sources,
    load_workforce,
)
from asteria.domain.objectives import ObjectiveError, ObjectiveRule, ObjectiveSpec, load_objectives
from asteria.sources import build_adapters
from asteria.sources.base import SourceAdapter


@dataclass
class Context:
    settings: Settings
    catalogue: SourceCatalogue
    countries: CountryCatalogue
    workforce: WorkforceConfig
    analysis: AnalysisConfig
    objectives: list[ObjectiveSpec]
    adapters: dict[str, SourceAdapter]


def load_context(settings: Settings | None = None) -> Context:
    """Load and cross-validate all configuration. Raises ConfigError on any problem."""
    settings = settings or Settings()
    catalogue = load_sources(settings.config_dir)
    analysis = load_analysis(settings.config_dir, catalogue)
    rules = {
        objective_id: ObjectiveRule(
            measure=r.measure,
            months=r.months,
            levels=tuple(r.levels) if r.levels else None,
            sensitivity_levels=tuple(r.sensitivity_levels) if r.sensitivity_levels else None,
        )
        for objective_id, r in analysis.objectives.items()
    }
    try:
        objectives = load_objectives(analysis.objectives_path(), rules)
    except ObjectiveError as exc:
        raise ConfigError(str(exc)) from exc
    return Context(
        settings=settings,
        catalogue=catalogue,
        countries=load_countries(settings.config_dir),
        workforce=load_workforce(settings.config_dir),
        analysis=analysis,
        objectives=objectives,
        adapters=build_adapters(catalogue),
    )
