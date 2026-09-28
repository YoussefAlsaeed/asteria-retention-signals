from pathlib import Path

import pytest

from asteria.config import ConfigError, CountryCatalogue, SourceCatalogue, load_sources


def test_repository_config_loads(catalogue: SourceCatalogue, countries: CountryCatalogue) -> None:
    assert len(catalogue.indicators) >= 3
    assert len(catalogue.providers) >= 2
    assert {c.code for c in countries.countries} == {"GR", "RO", "PL", "IT", "IE", "BG"}


def test_brief_minimums_hold(catalogue: SourceCatalogue) -> None:
    """Brief: at least two providers, three indicators, and two lenses."""
    used_providers = {i.provider for i in catalogue.indicators}
    assert len(used_providers) >= 2
    assert len({i.lens for i in catalogue.indicators}) >= 2


def test_country_aliases_map_to_canonical(countries: CountryCatalogue) -> None:
    assert countries.by_alias["EL"] == "GR"
    assert countries.by_alias["ROM"] == "RO"
    assert countries.by_alias["GR"] == "GR"


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "sources.yaml").write_text(
        """
providers: {}
history_start: "2019-01"
indicators:
  - {id: x, provider: nowhere, dataset: d, lens: labour_supply, title: t,
     frequency: M, unit: u, filters: {}}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown providers"):
        load_sources(tmp_path)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "sources.yaml").write_text(
        'providers: {}\nhistory_start: "2019-01"\nindicators: []\ntypo_field: 1\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="typo_field"):
        load_sources(tmp_path)


def test_missing_config_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="sources.yaml"):
        load_sources(tmp_path)
