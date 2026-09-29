"""Recompute every number in docs/findings.md without using the pipeline's code.

Run: uv run python scripts/verify_findings.py

Reads only the curated CSVs (employees.csv, external_observations.csv) and the analysis
config, then redoes the calculations with pandas (cohorts, turnover, point-in-time join via
merge_asof) and statsmodels formulas. Each result is compared with the pipeline's own outputs
(objective_measures.csv, association_results.csv). Exit code 1 if anything disagrees.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import yaml
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint
from statsmodels.tools.sm_exceptions import ConvergenceWarning

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
AS_OF = pd.Timestamp("2025-12-31")
START = pd.Timestamp("2021-01-01")
CONFIG = yaml.safe_load((ROOT / "config" / "analysis.yaml").read_text(encoding="utf-8"))

checks: list[tuple[str, float, float, bool]] = []


def check(label: str, pipeline: float, independent: float, tol: float = 1e-6) -> None:
    ok = bool(np.isclose(pipeline, independent, atol=tol, rtol=0))
    checks.append((label, pipeline, independent, ok))


# ---------------------------------------------------------------- inputs
emp = pd.read_csv(CURATED / "employees.csv", parse_dates=["hire_date", "exit_date"])
emp = emp[emp["is_measurable"]]
measures = pd.read_csv(CURATED / "objective_measures.csv")
assoc = pd.read_csv(CURATED / "association_results.csv")


def pipeline_rate(objective: str, year: int, country: str = "ALL", variant: str = "main",
                  segment: str = "All") -> float:  # fmt: skip
    row = measures[
        (measures.objective_id == objective) & (measures.variant == variant)
        & (measures.grain == "year") & (measures.country_code == country)
        & (measures.segment_value == segment) & (measures.period_start == f"{year}-01-01")
    ]  # fmt: skip
    assert len(row) == 1, (objective, year, country, variant, segment)
    return float(row["rate"].iloc[0])


# ---------------------------------------------------------------- findings 1-2: cohorts
def cohort(months: int, levels: list[str] | None, years: list[int],
           country: str | None = None, segment: str | None = None) -> tuple[int, int]:  # fmt: skip
    c = emp[emp.hire_date.dt.year.isin(years)]
    if levels:
        c = c[c.career_level.isin(levels)]
    if country:
        c = c[c.in_country_scope & (c.country_code == country)]
    if segment:
        c = c[c.business_unit == segment]
    lost = c.exit_date.notna() & (c.exit_date < c.hire_date + pd.DateOffset(months=months))
    return int((~lost).sum()), len(c)


MATURE = [2021, 2022, 2023, 2024]
for year in MATURE:
    k, n = cohort(12, ["Senior Leader"], [year])
    check(f"F1 senior 12m {year}", pipeline_rate("SENIOR_HIRE_12M", year), k / n)
    k, n = cohort(12, ["Senior Leader", "Manager"], [year])
    check(f"F1 senior+manager 12m {year}",
          pipeline_rate("SENIOR_HIRE_12M", year, variant="sensitivity_manager"), k / n)  # fmt: skip
    k, n = cohort(6, None, [year])
    check(f"F2 new hire 6m {year}", pipeline_rate("NEW_HIRE_6M", year), k / n)

pooled = {}
for label, months, levels in [("senior", 12, ["Senior Leader"]),
                              ("senior+manager", 12, ["Senior Leader", "Manager"]),
                              ("new hire", 6, None)]:  # fmt: skip
    k, n = cohort(months, levels, MATURE)
    low, high = proportion_confint(k, n, method="wilson")
    pooled[label] = (k, n, k / n, low, high)

for country in ["GR", "RO", "PL", "IT", "IE", "BG"]:
    k, n = cohort(6, None, MATURE, country=country)
    pooled[f"new hire {country}"] = (k, n, k / n, *proportion_confint(k, n, method="wilson"))
    for year in MATURE:
        kk, nn = cohort(6, None, [year], country=country)
        check(f"F2 new hire 6m {year} {country}",
              pipeline_rate("NEW_HIRE_6M", year, country=country), kk / nn)  # fmt: skip
for unit in ["Digital", "Finance", "Sales", "Supply Chain"]:
    k, n = cohort(6, None, MATURE, segment=unit)
    pooled[f"new hire {unit}"] = (k, n, k / n, *proportion_confint(k, n, method="wilson"))


# ---------------------------------------------------------------- finding 3: turnover
def turnover(year: int, country: str | None = None) -> tuple[int, float]:
    e = emp[emp.in_country_scope & (emp.country_code == country)] if country else emp
    ends = pd.date_range(f"{year}-01-31", f"{year}-12-31", freq="ME")
    headcount = np.mean([((e.hire_date <= d) & (e.exit_date.isna() | (e.exit_date > d))).sum()
                         for d in ends])  # fmt: skip
    regretted = ((e.regretted_status == "regretted") & (e.exit_date.dt.year == year)).sum()
    return int(regretted), float(headcount)


for year in [2021, 2022, 2023, 2024, 2025]:
    k, hc = turnover(year)
    check(f"F3 turnover Dec {year}", pipeline_rate("REGRETTED_TURNOVER_12M", year), k / hc)
for country in ["GR", "RO", "PL", "IT", "IE", "BG"]:
    k, hc = turnover(2025, country)
    check(f"F3 turnover 2025 {country}",
          pipeline_rate("REGRETTED_TURNOVER_12M", 2025, country=country), k / hc)  # fmt: skip


# ---------------------------------------------------------------- finding 4: associations
obs = pd.read_csv(CURATED / "external_observations.csv", parse_dates=["period_start", "period_end"])


def signal_frame(indicator: str, lag_days: int, release: str | None) -> pd.DataFrame:
    s = obs[obs.indicator_id == indicator]
    s = s[s.release_code == release] if release else s[s.release_code.isna()]
    s = s.assign(available_from=s.period_end + pd.Timedelta(days=lag_days))
    return s[["country_code", "available_from", "value"]].sort_values("available_from")


def attach(people: pd.DataFrame, signal: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time join: latest value whose available_from <= as_of_date, per country."""
    people = people.sort_values("as_of_date")
    joined = pd.merge_asof(people, signal, left_on="as_of_date", right_on="available_from",
                           by="country_code", direction="backward")  # fmt: skip
    return joined.dropna(subset=["value"])


in_scope = emp[emp.in_country_scope]


def cohort_people(months: int, levels: list[str] | None) -> pd.DataFrame:
    c = in_scope[in_scope.hire_date >= START]
    c = c[c.career_level.isin(levels)] if levels else c
    month = c.hire_date.dt.to_period("M").dt.start_time
    mature = (month + pd.offsets.MonthEnd(0) + pd.DateOffset(months=months)) <= AS_OF
    c, month = c[mature], month[mature]
    lost = c.exit_date.notna() & (c.exit_date < c.hire_date + pd.DateOffset(months=months))
    return pd.DataFrame(
        {"country_code": c.country_code, "as_of_date": month, "event": lost.astype(int)}
    )


def person_months() -> pd.DataFrame:
    months = pd.DataFrame({"as_of_date": pd.date_range(START, "2025-12-01", freq="MS")})
    grid = in_scope[["country_code", "hire_date", "exit_date", "regretted_status"]].merge(
        months, how="cross"
    )
    at_risk = (grid.hire_date < grid.as_of_date) & (
        grid.exit_date.isna() | (grid.exit_date >= grid.as_of_date)
    )
    grid = grid[at_risk]
    month_end = grid.as_of_date + pd.offsets.MonthEnd(0)
    event = (grid.exit_date <= month_end) & (grid.regretted_status == "regretted")
    return pd.DataFrame(
        {
            "country_code": grid.country_code,
            "as_of_date": grid.as_of_date,
            "event": event.astype(int),
        }
    )


samples = {
    "NEW_HIRE_6M": cohort_people(6, None),
    "SENIOR_HIRE_12M": cohort_people(12, ["Senior Leader"]),
    "REGRETTED_TURNOVER_12M": person_months(),
}
refit = []
for objective, people in samples.items():
    for sig in CONFIG["signals"]:
        df = attach(people, signal_frame(sig["indicator"], sig["lag_days"], sig.get("release")))
        cells = df[["country_code", "as_of_date", "value"]].drop_duplicates()
        sd = (cells.value - cells.groupby("country_code").value.transform("mean")).std(ddof=1)
        df = df.assign(x=df.value / sd,
                       trend=(df.as_of_date.dt.year - 2021) * 12 + df.as_of_date.dt.month - 1,
                       cluster=df.country_code + df.as_of_date.dt.strftime("%Y-%m"))  # fmt: skip
        groups = pd.factorize(df.cluster)[0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            fit = smf.glm("event ~ x + C(country_code) + trend", df,
                          family=sm.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": groups})  # fmt: skip
        refit.append((objective, sig["indicator"], len(df), int(df.event.sum()),
                      float(np.exp(fit.params["x"])), float(fit.pvalues["x"])))  # fmt: skip

q_values = multipletests([r[5] for r in refit], method="fdr_bh")[1]
for (objective, indicator, n, events, odds, _p), q in zip(refit, q_values, strict=True):
    row = assoc[(assoc.objective_id == objective) & (assoc.indicator_id == indicator)
                & (assoc.model == "within_country")].iloc[0]  # fmt: skip
    tag = f"F4 {objective} x {indicator}"
    check(f"{tag} n", row.n_obs, n, tol=0)
    check(f"{tag} events", row.n_events, events, tol=0)
    check(f"{tag} odds ratio", row.odds_ratio, odds, tol=1e-4)
    check(f"{tag} q", row.q_value, q, tol=1e-4)


# ---------------------------------------------------------------- report
print("Pooled 2021-2024 (numbers quoted in docs/findings.md):")
for label, (k, n, rate, low, high) in pooled.items():
    print(f"  {label:24} {k:>5} / {n:<5} = {rate:6.1%}   95% CI {low:6.1%} - {high:6.1%}")
print()
width = max(len(c[0]) for c in checks)
for label, pipeline, independent, ok in checks:
    print(
        f"  {'OK ' if ok else 'BAD'} {label:{width}}"
        f"  pipeline={pipeline:.6g}  independent={independent:.6g}"
    )
bad = [c for c in checks if not c[3]]
print(f"\n{len(checks) - len(bad)} of {len(checks)} checks agree.")
sys.exit(1 if bad else 0)
