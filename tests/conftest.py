from pathlib import Path

import pytest

from asteria.config import (
    CountryCatalogue,
    Indicator,
    SourceCatalogue,
    load_countries,
    load_sources,
)

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
