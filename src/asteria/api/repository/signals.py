"""Queries over point-in-time signals and association results."""

from __future__ import annotations

from typing import Any

from asteria.api.repository.base import BaseRepository


class SignalQueries(BaseRepository):
    def signal_series(self, indicator_id: str, countries: list[str]) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT country_code, as_of_date, value, signal_frequency, signal_period_start,
                   signal_period_end, signal_age_days, signal_status_label
            FROM mart_signal_asof
            WHERE indicator_id = ? AND list_contains(?, country_code)
              AND as_of_date >= (SELECT reporting_start FROM cfg_analysis)
            ORDER BY country_code, as_of_date
            """,
            [indicator_id, countries],
        )

    def associations(self, objective_id: str) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT indicator_id, model, outcome, n_obs, n_events, n_clusters,
                   signal_sd_within, odds_ratio, ci_low, ci_high, p_value, q_value, note
            FROM mart_association_results WHERE objective_id = ?
            ORDER BY indicator_id, model DESC
            """,
            [objective_id],
        )

    def association_cells(self, objective_id: str, indicator_id: str) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT country_code, period_start, n, events, event_rate, signal_mean
            FROM mart_association_cells WHERE objective_id = ? AND indicator_id = ?
            ORDER BY country_code, period_start
            """,
            [objective_id, indicator_id],
        )
