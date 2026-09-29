from pathlib import Path

import pytest

from asteria.config import ROOT
from asteria.domain.objectives import ObjectiveError, ObjectiveRule, load_objectives

FILE = ROOT / "data" / "raw-or-fixtures" / "starter" / "retention_objectives.csv"
RULES = {
    "NEW_HIRE_6M": ObjectiveRule("cohort_retention", 6),
    "SENIOR_HIRE_12M": ObjectiveRule("cohort_retention", 12, ("Senior Leader",)),
    "REGRETTED_TURNOVER_12M": ObjectiveRule("trailing_regretted_turnover", 12),
}


def test_targets_come_from_the_starter_file() -> None:
    specs = {s.objective_id: s for s in load_objectives(FILE, RULES)}
    assert (specs["NEW_HIRE_6M"].target, specs["NEW_HIRE_6M"].direction) == (0.86, "at_least")
    assert (specs["SENIOR_HIRE_12M"].target, specs["SENIOR_HIRE_12M"].months) == (0.90, 12)
    turnover = specs["REGRETTED_TURNOVER_12M"]
    assert (turnover.target, turnover.direction) == (0.075, "at_most")
    assert turnover.is_met(0.075) and not turnover.is_met(0.0751)


def test_config_and_file_must_name_the_same_objectives() -> None:
    with pytest.raises(ObjectiveError, match="do not match"):
        load_objectives(FILE, {"NEW_HIRE_6M": RULES["NEW_HIRE_6M"]})


def test_unknown_direction_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "o.csv"
    bad.write_text(
        FILE.read_text(encoding="utf-8").replace("at_least", "roughly", 1), encoding="utf-8"
    )
    with pytest.raises(ObjectiveError, match="unknown direction"):
        load_objectives(bad, RULES)
