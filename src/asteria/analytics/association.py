"""Association between external signals and retention outcomes.

Unit of analysis is the person (or person-month), never an averaged cell, so sample size is
honest. For each objective x signal two logistic models are fitted:

- ``naive``: outcome ~ signal. Pooled across countries: mixes between-country differences
  (culture, labour law, company practice) with the signal.
- ``within_country``: outcome ~ signal + country fixed effects + linear time trend. Asks
  whether months with a higher signal *within the same country* show different outcomes,
  net of a common drift over time.

The signal is identical for everyone in the same country and month, so observations are
not independent: standard errors are clustered on (country, month). Signals are scaled per
one within-country standard deviation, so odds ratios are comparable across indicators.
Benjamini-Hochberg q-values control the false discovery rate across all within-country
tests. None of this identifies causation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from statsmodels.tools.sm_exceptions import ConvergenceWarning, PerfectSeparationWarning

Z95 = 1.959963984540054


@dataclass
class AssociationResult:
    objective_id: str
    indicator_id: str
    model: str
    outcome: str
    n_obs: int
    n_events: int
    n_clusters: int
    signal_sd_within: float | None
    odds_ratio: float | None
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    q_value: float | None
    note: str


OUTCOMES = {
    "NEW_HIRE_6M": "exit within 6 months of hire",
    "SENIOR_HIRE_12M": "exit within 12 months of hire",
    "REGRETTED_TURNOVER_12M": "regretted exit in the month (per person-month at risk)",
}


def fit_associations(frame: pd.DataFrame, reporting_start: pd.Timestamp) -> list[AssociationResult]:
    """frame columns: objective_id, indicator_id, country_code, as_of_date, event, value."""
    results: list[AssociationResult] = []
    for (objective_id, indicator_id), group in frame.groupby(["objective_id", "indicator_id"]):
        results += _fit_pair(str(objective_id), str(indicator_id), group, reporting_start)

    tested = [r for r in results if r.model == "within_country" and r.p_value is not None]
    if tested:
        _, q_values, _, _ = multipletests([r.p_value for r in tested], method="fdr_bh")
        for result, q in zip(tested, q_values, strict=True):
            result.q_value = _round(float(q))
    return results


def _fit_pair(
    objective_id: str, indicator_id: str, df: pd.DataFrame, reporting_start: pd.Timestamp
) -> list[AssociationResult]:
    df = df.dropna(subset=["value"]).copy()
    base: dict[str, Any] = dict(
        objective_id=objective_id,
        indicator_id=indicator_id,
        outcome=OUTCOMES[objective_id],
        n_obs=len(df),
        n_events=int(df["event"].sum()),
    )

    # Scale by the within-country SD of the signal across distinct (country, month) cells.
    cells = df[["country_code", "as_of_date", "value"]].drop_duplicates()
    within = cells["value"] - cells.groupby("country_code")["value"].transform("mean")
    sd = float(within.std(ddof=1)) if len(cells) > 2 else float("nan")
    if not np.isfinite(sd) or sd == 0 or base["n_events"] == 0:
        note = "no within-country variation" if base["n_events"] else "no events"
        return [
            AssociationResult(**base, model=m, n_clusters=0, signal_sd_within=None,
                              odds_ratio=None, ci_low=None, ci_high=None, p_value=None,
                              q_value=None, note=note)
            for m in ("naive", "within_country")
        ]  # fmt: skip

    df["x"] = df["value"] / sd
    as_of = pd.to_datetime(df["as_of_date"])
    df["trend"] = (as_of.dt.year - reporting_start.year) * 12 + (
        as_of.dt.month - reporting_start.month
    )
    clusters = pd.factorize(df["country_code"] + "|" + as_of.dt.strftime("%Y-%m"))[0]

    naive = sm.add_constant(df[["x"]].astype(float))
    fixed = pd.get_dummies(df["country_code"], prefix="c", drop_first=True, dtype=float)
    within_x = sm.add_constant(pd.concat([df[["x", "trend"]].astype(float), fixed], axis=1))

    out = []
    for model, design in (("naive", naive), ("within_country", within_x)):
        out.append(_logit(df["event"].astype(float), design, clusters, base, model, _round(sd)))
    return out


def _logit(
    y: pd.Series, X: pd.DataFrame, clusters: np.ndarray, base: dict[str, Any], model: str,
    sd: float,
) -> AssociationResult:  # fmt: skip
    n_clusters = int(len(np.unique(clusters)))
    try:
        with warnings.catch_warnings():
            # Separation or non-convergence must fail the model visibly, not pass silently.
            warnings.simplefilter("error", ConvergenceWarning)
            warnings.simplefilter("error", PerfectSeparationWarning)
            fit = sm.GLM(y, X, family=sm.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": clusters}
            )
        beta, se, p = float(fit.params["x"]), float(fit.bse["x"]), float(fit.pvalues["x"])
    except Exception as exc:  # noqa: BLE001 - reported per model, never hidden
        return AssociationResult(
            **base, model=model, n_clusters=n_clusters, signal_sd_within=sd, odds_ratio=None,
            ci_low=None, ci_high=None, p_value=None, q_value=None,
            note=f"model failed: {type(exc).__name__}: {exc}"[:200],
        )  # fmt: skip
    return AssociationResult(
        **base,
        model=model,
        n_clusters=n_clusters,
        signal_sd_within=sd,
        odds_ratio=_round(float(np.exp(beta))),
        ci_low=_round(float(np.exp(beta - Z95 * se))),
        ci_high=_round(float(np.exp(beta + Z95 * se))),
        p_value=_round(p),
        q_value=None,
        note="",
    )


def _round(value: float) -> float:
    return float(f"{value:.6g}")
