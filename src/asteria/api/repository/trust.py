"""Queries behind the Data trust view: freshness, quality rules, workforce counts."""

from __future__ import annotations

from typing import Any

from asteria.api.repository.base import BaseRepository


class TrustQueries(BaseRepository):
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
