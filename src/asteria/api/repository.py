"""Read-only access to the analytical product. All SQL the API runs lives here.

Each call opens a short read-only DuckDB connection, so the API never holds a lock that
would block `asteria run` from rebuilding the file, and every query is parameterised.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

REQUIRED_TABLES = {
    "employees",
    "external_coverage",
    "external_observations",
    "mart_objective_measures",
    "mart_signal_asof",
    "mart_association_results",
    "mart_association_cells",
    "cfg_rules",
    "wf_quality_events",
    "ex_quality_events",
}


class DataNotReady(Exception):
    """The analytical product has not been built (or is incomplete)."""


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if not self.db_path.exists():
            raise DataNotReady(f"{self.db_path.name} not found")
        try:
            con = duckdb.connect(str(self.db_path), read_only=True)
        except duckdb.IOException as exc:  # e.g. locked while `asteria run` rebuilds it
            raise DataNotReady(f"database unavailable: {exc}") from exc
        try:
            yield con
        finally:
            con.close()

    def _rows(self, query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        with self._connect() as con:
            try:
                cursor = con.execute(query, params or [])
            except duckdb.CatalogException as exc:
                raise DataNotReady(f"analytical tables missing: {exc}") from exc
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def missing_tables(self) -> set[str]:
        rows = self._rows("SELECT table_name FROM information_schema.tables")
        return REQUIRED_TABLES - {r["table_name"] for r in rows}

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

    def freshness(self) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT c.indicator_id, any_value(c.frequency) AS frequency,
                   count(DISTINCT c.country_code) AS countries,
                   min(c.first_period_start) AS first_period, max(c.last_period_end) AS last_period,
                   sum(c.gaps)::INTEGER AS gaps, max(c.source_updated) AS source_updated,
                   max(c.loaded_at) AS loaded_at,
                   (SELECT count(*) FROM external_observations AS o
                    WHERE o.indicator_id = c.indicator_id
                      AND o.status IS NOT NULL) AS flagged_values,
                   (SELECT string_agg(DISTINCT o.status_label, '; ' ORDER BY o.status_label)
                    FROM external_observations AS o
                    WHERE o.indicator_id = c.indicator_id) AS flag_labels
            FROM external_coverage AS c
            WHERE c.release_code IS NULL OR c.release_code = 'FIN'
            GROUP BY c.indicator_id ORDER BY c.indicator_id
            """
        )

    def quality_rules(self) -> list[dict[str, Any]]:
        return self._rows(
            """
            WITH hits AS (
                SELECT rule_id, count(*) AS n FROM wf_quality_events GROUP BY rule_id
                UNION ALL SELECT rule_id, count(*) FROM ex_quality_events GROUP BY rule_id
            )
            SELECT r.rule_id, r.domain, r.severity, r.description,
                   coalesce(sum(h.n), 0)::INTEGER AS rows_affected
            FROM cfg_rules AS r LEFT JOIN hits AS h USING (rule_id)
            GROUP BY r.rule_id, r.domain, r.severity, r.description, r.position
            ORDER BY r.position
            """
        )

    def workforce_counts(self) -> dict[str, int]:
        row = self._rows(
            """
            SELECT count(*) AS employees,
                   count(*) FILTER (WHERE is_measurable) AS measurable,
                   count(*) FILTER (WHERE in_country_scope) AS in_country_scope
            FROM employees
            """
        )[0]
        return {k: int(v) for k, v in row.items()}
