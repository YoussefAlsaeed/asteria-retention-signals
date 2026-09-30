"""Filter options for the dashboard, assembled from configuration and the data."""

from __future__ import annotations

from asteria.api.repository import Repository
from asteria.api.schemas import CountryInfo, Meta, ObjectiveInfo, SignalInfo
from asteria.context import Context


def build_meta(ctx: Context, repo: Repository) -> Meta:
    variants = repo.variants()
    return Meta(
        as_of_date=ctx.workforce.as_of_date,
        reporting_start=ctx.analysis.reporting_start,
        min_sample=ctx.analysis.min_sample,
        objectives=[
            ObjectiveInfo(
                objective_id=o.objective_id,
                name=o.name,
                measure=o.measure,
                months=o.months,
                direction=o.direction,
                target=o.target,
                variants=variants.get(o.objective_id, ["main"]),
            )
            for o in ctx.objectives
        ],
        countries=[CountryInfo(code=c.code, name=c.name) for c in ctx.countries.countries],
        segment_name=ctx.analysis.segment,
        segments=repo.segments(),
        grains=["month", "quarter", "year"],
        signals=[_signal_info(ctx, s.indicator, s.lag_days) for s in ctx.analysis.signals],
    )


def _signal_info(ctx: Context, indicator_id: str, lag_days: int) -> SignalInfo:
    indicator = ctx.catalogue.indicator(indicator_id)
    return SignalInfo(
        indicator_id=indicator_id,
        title=indicator.title,
        lens=indicator.lens,
        unit=indicator.unit,
        frequency=indicator.frequency,
        provider=ctx.catalogue.providers[indicator.provider].name,
        lag_days=lag_days,
    )
