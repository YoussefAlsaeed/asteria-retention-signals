# AI usage

Running log of how an AI coding agent was used and verified. No secrets or transcripts.

## Tools

Claude Code (VS Code extension), model Claude Opus 5.5.

## Session log

1. **Brief analysis.** The agent summarised the brief, proposed an architecture, and listed the planted data defects by reading the data generator embedded in the brief HTML. *Not yet validated against the CSVs.* It classified `EL` as Eurostat's code for Greece (a mapping, not an error).
2. **Repository structure (suggestion changed).** The agent proposed a custom layout. The human pointed out the brief's suggested shape. The layout was reworked to use those top-level names, with domain boundaries inside `src/asteria/`.
3. **Repository initialisation.** Git's line-ending conversion would have altered the starter CSVs and broken their manifest checksums. `.gitattributes` now keeps data files byte-exact, and the checksums were verified on disk and in git.
4. **Scaffolding.** uv project, CLI stub, and tests. A file lock blocked a move, so the files were copied and their checksums re-verified. `pytest` 4/4, `ruff` clean.

## Suggestions rejected or changed

| Agent suggestion | Outcome |
|---|---|
| Custom repository layout | Changed to follow the brief's suggested shape |

## Verification

- Starter-pack SHA-256 checksums enforced by `tests/test_starter_data.py`.
- Data claims to be confirmed by profiling; external dataset codes and lags to be checked against provider sources.

## Remaining risks

- Defect inventory not yet confirmed against the data.
- External indicators and metric definitions not yet decided.

---

## Appendix: domain glossary

Agent-drafted, human-reviewed.

| Term | Plain meaning | Example |
|---|---|---|
| **Retention** | Keeping employees | "90% retention": 90 of 100 stayed |
| **Turnover** | People leaving | "10% turnover": 10 of 100 left |
| **Voluntary exit** | Employee chose to quit | Found a better job |
| **Involuntary exit** | Company let them go | Dismissal or layoff |
| **End of contract** | A temporary contract ended | One-year fixed-term contract finished |
| **Regretted exit** | Someone left whom the company wanted to keep | A strong engineer resigns |
| **Cohort** | A group sharing a start point, tracked together | Everyone hired in March 2023 |
| **Observation window** | Time that must pass before an outcome can be measured | Six-month retention needs six months |
| **Censoring** | Cut off before the window completes | Hired Oct 2025, data ends Dec 2025: outcome unknown |
| **Cohort maturity** | Whole cohort has passed its window | 2025-Q3 hires are not mature for a twelve-month objective |
| **Denominator** | The "out of how many" in a percentage | Regretted exits out of average headcount |
| **Average headcount** | Typical number of employees over a period | Month-end headcounts averaged over twelve months |
| **Trailing twelve months** | Twelve months ending on a given date | At June 2024: July 2023 to June 2024 |
| **Senior hire** | A newly hired manager or leader | Qualifying levels are a documented decision |
| **As-of date** | Date the data was frozen | 2025-12-31 |
| **Publication lag** | Delay between a period and its statistic's release | March data released in May can't explain April |
| **Frequency integrity** | Never present an annual value as monthly measurements | Carried-forward values keep their original period |
| **Association vs causation** | Moving together is not causing | Inflation and turnover can share a driver |

### Objectives

| Objective | Target | Plain meaning | Open decision |
|---|---|---|---|
| `NEW_HIRE_6M` | ≥ 0.86 | 86+ of 100 new hires still employed after six months | 182 days vs calendar months; immature cohorts |
| `SENIOR_HIRE_12M` | ≥ 0.90 | 90+ of 100 senior hires still employed after a year | Which levels qualify, incl. `Sr Mgmt` |
| `REGRETTED_TURNOVER_12M` | ≤ 0.075 | Regretted exits ≤ 7.5% of average headcount over twelve months | Headcount convention; unknown regretted flags |
