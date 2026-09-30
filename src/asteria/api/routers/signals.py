from __future__ import annotations

from fastapi import APIRouter

from asteria.api.dependencies import ContextDep, CountryDep, RepositoryDep, SignalDep, country_codes
from asteria.api.schemas import SignalPoint, SignalSeries

router = APIRouter(prefix="/api", tags=["signals"])


@router.get("/signals/{indicator_id}", response_model=list[SignalSeries])
def signal_series(
    signal: SignalDep, ctx: ContextDep, repo: RepositoryDep, country: CountryDep
) -> list[SignalSeries]:
    """A signal as it was known at the start of each month, per country."""
    wanted = list(country_codes(ctx)) if country == "ALL" else [country]
    rows = repo.signal_series(signal.indicator, wanted)
    return [
        SignalSeries(
            country=code,
            points=[
                SignalPoint(**{k: v for k, v in r.items() if k != "country_code"})
                for r in rows
                if r["country_code"] == code
            ],
        )
        for code in wanted
    ]
