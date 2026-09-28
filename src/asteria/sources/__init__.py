"""Source adapters: one per external provider, behind a common interface."""

from datetime import date

from asteria.config import ConfigError, SourceCatalogue
from asteria.sources.base import SourceAdapter
from asteria.sources.eurostat import EurostatAdapter
from asteria.sources.worldbank import WorldBankAdapter


def build_adapters(
    catalogue: SourceCatalogue, today: date | None = None
) -> dict[str, SourceAdapter]:
    """One adapter per configured provider. Unknown providers fail loudly."""
    adapters: dict[str, SourceAdapter] = {}
    for provider_id, provider in catalogue.providers.items():
        if provider_id == "eurostat":
            adapters[provider_id] = EurostatAdapter(provider.base_url)
        elif provider_id == "worldbank":
            end_year = (today or date.today()).year
            adapters[provider_id] = WorldBankAdapter(provider.base_url, end_year)
        else:
            raise ConfigError(f"no adapter implemented for provider '{provider_id}'")
    return adapters
