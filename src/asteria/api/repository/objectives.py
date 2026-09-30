"""Queries over the objective measures (`mart_objective_measures`)."""

from __future__ import annotations

from typing import Any

from asteria.api.repository.base import BaseRepository


class ObjectiveQueries(BaseRepository):
    def segments(self) -> list[str]:
        rows = self._rows(
            "SELECT DISTINCT segment_value FROM mart_objective_measures"
            " WHERE segment_value <> 'All' ORDER BY 1"
        )
        return [r["segment_value"] for r in rows]

    def variants(self) -> dict[str, list[str]]:
        """Available definitions per objective, 'main' first."""
        rows = self._rows(
            "SELECT DISTINCT objective_id, variant FROM mart_objective_measures"
            " ORDER BY objective_id, variant"
        )
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["objective_id"], []).append(r["variant"])
        return {
            k: sorted(v, key=lambda variant: (variant != "main", variant)) for k, v in out.items()
        }

    def measures(
        self, objective_id: str, country: str, segment: str, grain: str, variant: str
    ) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT period_start, period_end, numerator, denominator, rate, ci_low, ci_high,
                   status, confidence
            FROM mart_objective_measures
            WHERE objective_id = ? AND country_code = ? AND segment_value = ? AND grain = ?
              AND variant = ?
            ORDER BY period_start
            """,
            [objective_id, country, segment, grain, variant],
        )

    def latest_status(self, country: str, segment: str, grain: str) -> list[dict[str, Any]]:
        """Most recent measured (non-pending) period per objective, main definition."""
        return self._rows(
            """
            SELECT objective_id, period_start, period_end, numerator, denominator, rate,
                   ci_low, ci_high, target, direction, status, confidence,
                   (SELECT count(*) FROM mart_objective_measures AS p
                    WHERE p.objective_id = m.objective_id AND p.variant = 'main'
                      AND p.grain = m.grain AND p.country_code = m.country_code
                      AND p.segment_value = m.segment_value
                      AND p.status = 'pending') AS pending_periods
            FROM mart_objective_measures AS m
            WHERE variant = 'main' AND country_code = ? AND segment_value = ? AND grain = ?
              AND status <> 'pending'
            QUALIFY row_number() OVER (PARTITION BY objective_id ORDER BY period_start DESC) = 1
            ORDER BY objective_id
            """,
            [country, segment, grain],
        )

    def pooled_cohorts(self) -> list[dict[str, Any]]:
        """Hire-based objectives pooled over complete (non-pending) hire years, company-wide."""
        return self._rows(
            """
            SELECT objective_id, variant,
                   sum(numerator) AS numerator, sum(denominator) AS denominator,
                   sum(numerator) / sum(denominator) AS rate,
                   wilson_low(sum(numerator)::DOUBLE, sum(denominator)) AS ci_low,
                   wilson_high(sum(numerator)::DOUBLE, sum(denominator)) AS ci_high,
                   min(year(period_start)) AS first_year, max(year(period_start)) AS last_year,
                   list(rate ORDER BY period_start) AS yearly_rates
            FROM mart_objective_measures AS m
            JOIN cfg_objectives AS o USING (objective_id)
            WHERE o.measure = 'cohort_retention' AND grain = 'year' AND country_code = 'ALL'
              AND segment_value = 'All' AND status <> 'pending'
            GROUP BY objective_id, variant
            ORDER BY objective_id, variant
            """
        )

    def yearly_turnover(self) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT year(period_end) AS year, numerator, denominator, rate, ci_low, ci_high,
                   status, confidence
            FROM mart_objective_measures
            WHERE objective_id = 'REGRETTED_TURNOVER_12M' AND variant = 'main' AND grain = 'year'
              AND country_code = 'ALL' AND segment_value = 'All'
            ORDER BY period_end
            """
        )
