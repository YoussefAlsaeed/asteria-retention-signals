"""The Key findings summary: pooled objectives plus a roll-up of the association tests."""

from __future__ import annotations

from collections.abc import Iterable

from asteria.api.repository import Repository
from asteria.api.schemas import AssociationRow, Findings, PooledCohort, TurnoverYear

# Fixed before looking at results: q below this counts as "associated after correction".
SIGNIFICANCE_Q = 0.05


def build_findings(repo: Repository, objective_ids: Iterable[str]) -> Findings:
    within = [
        {**row, "objective_id": objective_id}
        for objective_id in objective_ids
        for row in repo.associations(objective_id)
        if row["model"] == "within_country" and row["q_value"] is not None
    ]
    strongest = min(within, key=lambda r: r["p_value"]) if within else None
    return Findings(
        pooled=[PooledCohort(**row) for row in repo.pooled_cohorts()],
        turnover=[TurnoverYear(**row) for row in repo.yearly_turnover()],
        association_tests=len(within),
        association_significant=sum(1 for r in within if r["q_value"] < SIGNIFICANCE_Q),
        smallest_q=min((r["q_value"] for r in within), default=None),
        strongest=(
            AssociationRow(**{k: v for k, v in strongest.items() if k != "objective_id"})
            if strongest
            else None
        ),
        strongest_objective=strongest["objective_id"] if strongest else None,
    )
