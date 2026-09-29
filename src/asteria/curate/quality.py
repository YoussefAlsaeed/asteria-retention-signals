"""Data-quality rule catalogue.

Severity decides what happens to an affected row:

- ``error``: the run fails (quality gate). Used where continuing would give wrong joins.
- ``exclude``: the row is kept in the canonical table but excluded from every measure.
- ``exclude_country``: excluded from country-level views; still counts company-wide.
- ``warn``: kept and measured; flagged so its effect can be shown.
- ``corrected``: a documented rule rewrote the value (for example a country alias).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "exclude", "exclude_country", "warn", "corrected"]


@dataclass(frozen=True)
class Rule:
    id: str
    domain: Literal["workforce", "external"]
    severity: Severity
    description: str


RULES = [
    # Workforce
    Rule(
        "WF_EXACT_DUPLICATE",
        "workforce",
        "corrected",
        "Row identical to an earlier row on every column; removed.",
    ),
    Rule(
        "WF_ID_SUPERSEDED",
        "workforce",
        "corrected",
        "Older version of an employee_id with conflicting values; latest record_updated_at kept.",
    ),
    Rule(
        "WF_COUNTRY_ALIAS",
        "workforce",
        "corrected",
        "Non-ISO country code mapped to its canonical code (EL to GR, ROM to RO).",
    ),
    Rule(
        "WF_COUNTRY_MISSING",
        "workforce",
        "exclude_country",
        "Blank country_code; cannot be joined to country signals.",
    ),
    Rule(
        "WF_COUNTRY_UNKNOWN",
        "workforce",
        "exclude_country",
        "country_code not in the configured operating countries.",
    ),
    Rule(
        "WF_CAREER_LEVEL_ALIAS",
        "workforce",
        "corrected",
        "Career level label mapped by a configured alias (Sr Mgmt to Senior Leader).",
    ),
    Rule(
        "WF_CATEGORY_UNKNOWN",
        "workforce",
        "warn",
        "Business unit, career level, employment type, termination type or source system "
        "outside the allowed values.",
    ),
    Rule(
        "WF_DATE_UNPARSEABLE",
        "workforce",
        "exclude",
        "hire_date or termination_date present but not a valid ISO date.",
    ),
    Rule(
        "WF_HIRE_DATE_MISSING",
        "workforce",
        "exclude",
        "Blank hire_date; the employee cannot be placed in any cohort.",
    ),
    Rule("WF_HIRE_AFTER_AS_OF", "workforce", "exclude", "hire_date after the as-of date."),
    Rule(
        "WF_TERMINATION_BEFORE_HIRE",
        "workforce",
        "exclude",
        "termination_date earlier than hire_date; impossible tenure.",
    ),
    Rule(
        "WF_TERMINATION_AFTER_AS_OF",
        "workforce",
        "warn",
        "termination_date after the as-of date; treated as active at the as-of date.",
    ),
    Rule(
        "WF_TERMINATION_TYPE_MISSING",
        "workforce",
        "warn",
        "termination_date present but termination_type blank; counts as an exit, "
        "never as regretted.",
    ),
    Rule(
        "WF_TYPE_WITHOUT_DATE",
        "workforce",
        "warn",
        "termination_type present but termination_date blank; treated as active.",
    ),
    Rule(
        "WF_REGRETTED_UNKNOWN",
        "workforce",
        "warn",
        "Voluntary exit with blank regretted_exit; unknown, not false.",
    ),
    Rule(
        "WF_REGRETTED_NOT_VOLUNTARY",
        "workforce",
        "warn",
        "regretted_exit = true on a non-voluntary exit.",
    ),
    Rule(
        "WF_EOC_ON_PERMANENT",
        "workforce",
        "warn",
        "End of Contract exit recorded for a Permanent employee.",
    ),
    # External
    Rule(
        "EX_GEO_UNMAPPED",
        "external",
        "error",
        "Provider geo code not mapped to a canonical country.",
    ),
    Rule(
        "EX_PERIOD_UNPARSEABLE",
        "external",
        "error",
        "Provider period string does not match the indicator's frequency.",
    ),
    Rule(
        "EX_GRAIN_DUPLICATE",
        "external",
        "error",
        "More than one value for the same indicator, country, period and release.",
    ),
    Rule("EX_VALUE_MISSING", "external", "warn", "Provider returned a status flag but no value."),
    Rule(
        "EX_PERIOD_GAP",
        "external",
        "warn",
        "Period missing inside a series' own first-to-last range.",
    ),
    Rule(
        "EX_STATUS_FLAGGED",
        "external",
        "warn",
        "Value carries a provider status flag (e.g. provisional, estimated, break).",
    ),
]

RULES_BY_ID = {rule.id: rule for rule in RULES}
EXCLUDING = {r.id for r in RULES if r.severity == "exclude"}
EXCLUDING_COUNTRY = {r.id for r in RULES if r.severity == "exclude_country"}
