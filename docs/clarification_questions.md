# Clarification questions

One batch, sent once ([clarification_questions.pdf](clarification_questions.pdf)). Only questions that can change a reported objective result are sent. Evidence from [data_profile.md](data_profile.md).

## Sent

| # | Question | Default assumption if unanswered |
|---|---|---|
| 1 | **Senior scope (`SENIOR_HIRE_12M`).** Which career levels count as senior hires: `Senior Leader` only, or also `Manager`? Is `Sr Mgmt` (10 records) an alias of `Senior Leader`? | `Senior Leader` plus `Sr Mgmt` mapped to it; `Manager` excluded. Sensitivity shown with `Manager` included. |
| 2 | **Cohort scope and maturity (`NEW_HIRE_6M`, `SENIOR_HIRE_12M`).** Are only hires from 2021-01-01 in scope (414 records were hired in 2020)? Should cohorts be monthly by hire date, reporting only cohorts whose full window has elapsed by 2025-12-31? | Monthly hire cohorts from 2021-01; only mature cohorts reported, immature shown as pending; 2020 hires excluded from cohorts but counted in headcount. |
| 3 | **Regretted turnover denominator (`REGRETTED_TURNOVER_12M`).** Is average headcount the mean of the 12 month-end headcounts in the trailing window, or the average of opening and closing headcount? | Mean of the 12 month-end headcounts. Numerator: voluntary exits flagged regretted within the window. |

## Not sent: documented assumptions

Low impact on results (few rows) or resolvable by a stated rule. Each is recorded, applied consistently, and reported in the quality output.

| Topic | Assumption |
|---|---|
| Six/twelve-month boundary | Calendar months from hire date; retained if still employed on the final day (about 2 exits fall in the ambiguous range) |
| Blank regretted flag on voluntary exits (2) | Main metric treats as not regretted; upper bound treats as regretted |
| Exits with blank termination type (13) | Count as exits for retention; not regretted; flagged |
| End of Contract on Permanent employees (90) | Accepted as exits; flagged as inconsistency; not reclassified |
| Termination before hire (5), blank hire date (5) | Excluded from all measures; counts reported |
| Reporting grain | Monthly measures, rolled up to quarter and year in the dashboard |
| Source systems `HCM_A` / `HCM_B` | Treated as equivalent; kept as a lineage and quality dimension |
