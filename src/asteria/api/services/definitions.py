"""Plain-language method definitions shown in the Data trust view, built from config."""

from __future__ import annotations

from asteria.context import Context


def method_definitions(ctx: Context) -> dict[str, str]:
    out = {}
    for o in ctx.objectives:
        if o.measure == "cohort_retention":
            levels = ", ".join(o.levels) if o.levels else "all career levels"
            out[o.objective_id] = (
                f"Share of hires ({levels}) still employed {o.months} calendar months after "
                "their hire date. Hires are grouped by hire month; a period is reported only "
                f"once every hire in it has reached {o.months} months (otherwise 'not yet "
                "observable')."
            )
        else:
            out[o.objective_id] = (
                "Regretted exits in the trailing 12 months divided by the mean of the 12 "
                "month-end headcounts in that window. Unknown regretted flags count as not "
                "regretted."
            )
    out["signals"] = (
        "Each month uses only values already published by its first day (period end plus "
        "a per-indicator publication lag). Carried-forward values keep their own period "
        "and age; annual figures are never shown as monthly measurements."
    )
    out["associations"] = (
        "Person-level logistic models with country fixed effects, a linear time trend, "
        "and standard errors clustered by country-month; q-values apply the "
        "Benjamini-Hochberg correction across all within-country tests. Association, "
        "not causation."
    )
    out["intervals"] = (
        f"Wilson 95% intervals. 'Too few people' below {ctx.analysis.min_sample} people."
    )
    return out
