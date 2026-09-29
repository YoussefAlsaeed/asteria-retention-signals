"""Known-answer tests for the association method on synthetic data."""

import numpy as np
import pandas as pd

from asteria.analytics.association import fit_associations

START = pd.Timestamp("2021-01-01")
COUNTRIES = ["GR", "RO", "PL", "IT", "IE", "BG"]
MONTHS = pd.date_range("2021-01-01", periods=48, freq="MS")


def panel(signal_effect: float, country_effect: float, seed: int, n: int = 40) -> pd.DataFrame:
    """n people per country-month; the signal has a country level plus monthly variation."""
    rng = np.random.default_rng(seed)
    rows = []
    for c_index, country in enumerate(COUNTRIES):
        level = c_index * 2.0  # countries differ strongly in signal level
        for month in MONTHS:
            wiggle = rng.normal()
            value = level + wiggle
            logit = -2.0 + signal_effect * wiggle + country_effect * level
            p = 1 / (1 + np.exp(-logit))
            events = rng.random(n) < p
            rows += [(country, month.date(), int(e), value) for e in events]
    df = pd.DataFrame(rows, columns=["country_code", "as_of_date", "event", "value"])
    df["objective_id"] = "NEW_HIRE_6M"
    df["indicator_id"] = "demo_signal"
    return df


def by_model(df: pd.DataFrame) -> dict[str, object]:
    return {r.model: r for r in fit_associations(df, START)}


def test_detects_a_real_within_country_effect() -> None:
    results = by_model(panel(signal_effect=0.5, country_effect=0.0, seed=1))
    within = results["within_country"]
    assert within.odds_ratio is not None and within.odds_ratio > 1.3
    assert within.p_value is not None and within.p_value < 0.001


def test_no_effect_is_not_reported_as_one() -> None:
    within = by_model(panel(signal_effect=0.0, country_effect=0.0, seed=2))["within_country"]
    assert within.ci_low is not None and within.ci_high is not None
    assert within.ci_low < 1 < within.ci_high


def test_country_confounding_fools_naive_but_not_within_country() -> None:
    """Outcome differs by country only; the signal just tracks the country level."""
    results = by_model(panel(signal_effect=0.0, country_effect=0.15, seed=3))
    naive, within = results["naive"], results["within_country"]
    assert naive.p_value is not None and naive.p_value < 0.001  # spurious
    assert within.ci_low is not None and within.ci_high is not None
    assert within.ci_low < 1 < within.ci_high  # correctly null


def test_clusters_are_country_months_and_q_values_are_filled() -> None:
    within = by_model(panel(signal_effect=0.0, country_effect=0.0, seed=4))["within_country"]
    assert within.n_clusters == len(COUNTRIES) * len(MONTHS)
    assert within.q_value is not None


def test_signal_without_variation_is_reported_not_fitted() -> None:
    df = panel(0.0, 0.0, seed=5)
    df["value"] = df["country_code"].map({c: i for i, c in enumerate(COUNTRIES)})
    for result in fit_associations(df, START):
        assert result.odds_ratio is None and "no within-country variation" in result.note
