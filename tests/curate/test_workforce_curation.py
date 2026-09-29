"""Each planted defect type, one row each, and what curation must do with it."""

from typing import Any

import duckdb
import pytest

from tests.curate.conftest import CurateFn

ROWS = [
    # id, country, level, type, hire, termination, term type, regretted, updated
    "E01,GR,Sales,Field Sales,Manager,Permanent,2022-01-10,,,,HCM_A,2025-12-20",
    "E01,GR,Sales,Field Sales,Manager,Permanent,2022-01-10,,,,HCM_A,2025-12-20",  # exact dup
    "E02,EL,Sales,Field Sales,Manager,Permanent,2022-01-10,,,,HCM_A,2025-12-20",
    "E03,,Sales,Field Sales,Manager,Permanent,2022-01-10,,,,HCM_A,2025-12-20",
    "E04,XX,Sales,Field Sales,Manager,Permanent,2022-01-10,,,,HCM_A,2025-12-20",
    "E05,RO,Digital,Data,Sr Mgmt,Permanent,2022-01-10,,,,HCM_B,2025-12-20",
    "E06,PL,Finance,Controls,Manager,Permanent,,,,,HCM_A,2025-12-20",
    "E07,IT,Finance,Controls,Manager,Permanent,2023-05-01,2023-04-20,Voluntary,true,HCM_A,2025-12-20",
    "E08,IE,Finance,Controls,Manager,Permanent,2023-05-01,2026-02-01,Voluntary,false,HCM_A,2025-12-20",
    "E09,BG,Finance,Controls,Manager,Permanent,2023-05-01,2023-08-01,,false,HCM_A,2025-12-20",
    "E10,GR,Finance,Controls,Manager,Permanent,2023-05-01,2024-01-15,Voluntary,,HCM_A,2025-12-20",
    "E11,GR,Finance,Controls,Manager,Permanent,2023-05-01,2024-01-15,Involuntary,true,HCM_A,2025-12-20",
    "E12,GR,Finance,Controls,Manager,Permanent,2023-05-01,2024-01-15,End of Contract,false,HCM_A,2025-12-20",
    "E13,GR,Finance,Controls,Manager,Permanent,2024-13-45,,,,HCM_A,2025-12-20",
    "E14,GR,Sales,Key Accounts,Manager,Permanent,2021-03-01,,,,HCM_A,2025-12-20",  # older
    "E14,GR,Sales,Key Accounts,Manager,Permanent,2021-03-01,2025-06-30,Voluntary,true,HCM_B,2025-12-28",
    "E15,GR,Sales,Key Accounts,Manager,Permanent,2021-03-01,2024-02-01,Voluntary,true,HCM_A,2025-12-20",
]  # fmt: skip


@pytest.fixture
def employees(run: CurateFn) -> dict[str, dict[str, Any]]:
    _, con = run(ROWS)
    return _rows(con, "SELECT * FROM employees")


def _rows(con: duckdb.DuckDBPyConnection, query: str) -> dict[str, dict[str, Any]]:
    cursor = con.execute(query)
    columns = [d[0] for d in cursor.description]
    return {row[0]: dict(zip(columns, row, strict=True)) for row in cursor.fetchall()}


def test_one_canonical_row_per_employee(employees: dict[str, dict[str, Any]]) -> None:
    assert sorted(employees) == [f"E{i:02d}" for i in range(1, 16)]


def test_clean_row_is_measurable_with_no_rules(employees: dict[str, dict[str, Any]]) -> None:
    e = employees["E01"]
    assert (e["is_measurable"], e["in_country_scope"], e["quality_rules"]) == (True, True, [])


def test_country_alias_is_corrected_and_kept_in_scope(employees: dict[str, dict[str, Any]]) -> None:
    e = employees["E02"]
    assert (e["country_code"], e["country_code_raw"]) == ("GR", "EL")
    assert e["quality_rules"] == ["WF_COUNTRY_ALIAS"] and e["in_country_scope"]


@pytest.mark.parametrize(("emp", "rule"), [("E03", "WF_COUNTRY_MISSING"),
                                           ("E04", "WF_COUNTRY_UNKNOWN")])  # fmt: skip
def test_bad_country_leaves_company_view_but_not_country_view(
    employees: dict[str, dict[str, Any]], emp: str, rule: str
) -> None:
    e = employees[emp]
    assert rule in e["quality_rules"]
    assert e["is_measurable"] and not e["in_country_scope"] and e["country_code"] is None


def test_level_alias(employees: dict[str, dict[str, Any]]) -> None:
    e = employees["E05"]
    assert (e["career_level"], e["career_level_raw"]) == ("Senior Leader", "Sr Mgmt")


@pytest.mark.parametrize(
    ("emp", "rule"),
    [("E06", "WF_HIRE_DATE_MISSING"), ("E07", "WF_TERMINATION_BEFORE_HIRE"),
     ("E13", "WF_DATE_UNPARSEABLE")],
)  # fmt: skip
def test_invalid_records_are_kept_but_excluded(
    employees: dict[str, dict[str, Any]], emp: str, rule: str
) -> None:
    e = employees[emp]
    assert rule in e["quality_rules"] and not e["is_measurable"] and not e["in_country_scope"]


def test_future_termination_is_not_known_at_as_of(employees: dict[str, dict[str, Any]]) -> None:
    e = employees["E08"]
    assert e["exit_date"] is None and e["exit_type"] is None
    assert e["regretted_status"] == "not_applicable"
    assert e["quality_rules"] == ["WF_TERMINATION_AFTER_AS_OF"] and e["is_measurable"]


def test_exit_without_type_counts_as_exit_but_never_regretted(
    employees: dict[str, dict[str, Any]],
) -> None:
    e = employees["E09"]
    assert e["exit_date"] is not None and e["exit_type"] is None
    assert e["regretted_status"] == "not_applicable"


@pytest.mark.parametrize(
    ("emp", "status", "rule"),
    [("E10", "unknown", "WF_REGRETTED_UNKNOWN"),
     ("E11", "not_applicable", "WF_REGRETTED_NOT_VOLUNTARY"),
     ("E12", "not_applicable", "WF_EOC_ON_PERMANENT"),
     ("E15", "regretted", None)],
)  # fmt: skip
def test_regretted_semantics(
    employees: dict[str, dict[str, Any]], emp: str, status: str, rule: str | None
) -> None:
    e = employees[emp]
    assert e["regretted_status"] == status
    assert e["quality_rules"] == ([rule] if rule else [])


def test_latest_version_of_an_employee_wins(employees: dict[str, dict[str, Any]]) -> None:
    e = employees["E14"]
    assert str(e["exit_date"]) == "2025-06-30" and e["source_system"] == "HCM_B"


def test_rule_counts_reconcile_with_rows_read(run: CurateFn) -> None:
    report, _ = run(ROWS)
    counts = {r.rule_id: r.rows_affected for r in report.rules}
    assert report.workforce_rows_read == len(ROWS)
    assert counts["WF_EXACT_DUPLICATE"] + counts["WF_ID_SUPERSEDED"] + report.employees == len(ROWS)
    assert report.measurable == report.employees - 3  # E06, E07, E13
