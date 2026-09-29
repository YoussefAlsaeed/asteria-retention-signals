"""Retention objectives: the business target (from the starter file) plus our metric rules.

Pure: no database, no network. Pipelines receive ObjectiveSpec values and never re-read
the targets file themselves, so target and metric definition cannot drift apart.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

Measure = Literal["cohort_retention", "trailing_regretted_turnover"]
Direction = Literal["at_least", "at_most"]


class ObjectiveError(ValueError):
    """Objective targets and metric configuration do not agree."""


@dataclass(frozen=True)
class ObjectiveRule:
    measure: Measure
    months: int
    levels: tuple[str, ...] | None = None
    sensitivity_levels: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ObjectiveSpec:
    objective_id: str
    name: str
    measure: Measure
    months: int
    direction: Direction
    target: float
    effective_from: date
    effective_to: date
    levels: tuple[str, ...] | None
    sensitivity_levels: tuple[str, ...] | None

    def is_met(self, rate: float) -> bool:
        return rate >= self.target if self.direction == "at_least" else rate <= self.target


def load_objectives(path: Path, rules: dict[str, ObjectiveRule]) -> list[ObjectiveSpec]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError as exc:
        raise ObjectiveError(f"objectives file not found: {path}") from exc

    ids = {row["objective_id"] for row in rows}
    if ids != rules.keys():
        raise ObjectiveError(
            f"objectives in {path.name} {sorted(ids)} do not match configured rules {sorted(rules)}"
        )

    specs = []
    for row in rows:
        rule = rules[row["objective_id"]]
        direction = row["direction"]
        if direction not in ("at_least", "at_most"):
            raise ObjectiveError(f"{row['objective_id']}: unknown direction '{direction}'")
        if row["unit"] != "proportion":
            raise ObjectiveError(f"{row['objective_id']}: unit '{row['unit']}' is not proportion")
        target = float(row["target_value"])
        if not 0 < target < 1:
            raise ObjectiveError(f"{row['objective_id']}: target {target} is not a proportion")
        specs.append(
            ObjectiveSpec(
                objective_id=row["objective_id"],
                name=row["objective_name"],
                measure=rule.measure,
                months=rule.months,
                direction=direction,  # type: ignore[arg-type]
                target=target,
                effective_from=date.fromisoformat(row["effective_from"]),
                effective_to=date.fromisoformat(row["effective_to"]),
                levels=rule.levels,
                sensitivity_levels=rule.sensitivity_levels,
            )
        )
    return sorted(specs, key=lambda s: s.objective_id)
