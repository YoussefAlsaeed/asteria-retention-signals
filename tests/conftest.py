from datetime import date
from pathlib import Path

import pytest

from asteria.analytics.pipeline import run_analyse
from asteria.config import (
    CountryCatalogue,
    Indicator,
    Settings,
    SourceCatalogue,
    load_countries,
    load_sources,
)
from asteria.context import load_context
from asteria.curate.pipeline import run_curate
from asteria.ingest.raw_store import RawStore
from asteria.sources import build_adapters

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


@pytest.fixture(scope="session")
def catalogue() -> SourceCatalogue:
    return load_sources(CONFIG)


@pytest.fixture(scope="session")
def countries() -> CountryCatalogue:
    return load_countries(CONFIG)


@pytest.fixture
def eurostat_indicator() -> Indicator:
    return Indicator(
        id="demo_rate",
        provider="eurostat",
        dataset="demo_ds",
        lens="labour_supply",
        title="Demo",
        frequency="M",
        unit="percent",
        filters={"freq": "M", "unit": "PC"},
    )


@pytest.fixture
def worldbank_indicator() -> Indicator:
    return Indicator(
        id="gdp_growth",
        provider="worldbank",
        dataset="NY.GDP.MKTP.KD.ZG",
        lens="economic_cycle",
        title="GDP growth",
        frequency="A",
        unit="percent",
        filters={},
    )


@pytest.fixture(scope="session")
def built_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A complete analytical product built from the committed inputs into a temp dir."""
    data_dir = tmp_path_factory.mktemp("data")
    ctx = load_context(Settings(data_dir=data_dir))
    adapters = build_adapters(ctx.catalogue, date(2026, 9, 28))
    run_curate(
        ctx.settings.curated_dir,
        ctx.catalogue,
        ctx.countries,
        ctx.workforce,
        adapters,
        RawStore(ROOT / "data" / "raw-or-fixtures" / "sources"),
    )
    run_analyse(ctx.settings.curated_dir, ctx.analysis, ctx.workforce, ctx.objectives)
    return data_dir
