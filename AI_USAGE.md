# AI usage

Running log of how an AI coding agent was used and verified. No secrets or transcripts.

## Tools

Claude Code (VS Code extension), model Claude Opus 5.5.

## Session log

1. **Brief analysis.** The agent summarised the brief, proposed an architecture, and listed the planted data defects by reading the data generator embedded in the brief HTML. *Not yet validated against the CSVs.* It classified `EL` as Eurostat's code for Greece (a mapping, not an error).
2. **Repository structure (suggestion changed).** The agent proposed a custom layout. The human pointed out the brief's suggested shape. The layout was reworked to use those top-level names, with domain boundaries inside `src/asteria/`.
3. **Repository initialisation.** Git's line-ending conversion would have altered the starter CSVs and broken their manifest checksums. `.gitattributes` now keeps data files byte-exact, and the checksums were verified on disk and in git.
4. **Scaffolding.** uv project, CLI stub, and tests. A file lock blocked a move, so the files were copied and their checksums re-verified. `pytest` 4/4, `ruff` clean.
5. **Rules file.** At the human's request, the agent extracted every rule from the brief into `CLAUDE.md`, which the agent loads each session, so requirements such as frequency integrity and censoring aren't lost as work grows. The human asked for full coverage; the agent re-checked the brief and added two missed items (business/engineering outcomes, submission access). The brief remains the source of truth.
6. **Data profiling (agent claims corrected).** `scripts/profile_starter_data.py` writes [docs/data_profile.md](docs/data_profile.md). The data disagreed with the agent's earlier generator-based expectations in three places: voluntary exits with a blank regretted flag are **2**, not "up to 12"; terminations after the as-of date are **0**, not "possible"; the claim that the six-month boundary "really moves the metric" was overstated, since no exits fall on days 181–182. Profiling also found a defect the agent had not listed: **90** End of Contract exits on Permanent employees.
7. **Generator disclosure (human insight).** The human noticed that the generator in the brief shows attrition is driven only by internal factors, not external data. The agent confirmed that the generator, re-run in Node, reproduces all three CSVs byte for byte. Decision: disclose this openly; do not use the formula as an analysis input; use it only to sanity-check that the pipeline recovers known internal effects and to frame external associations as non-causal.
8. **Clarification questions.** [docs/clarification_questions.md](docs/clarification_questions.md): ten questions, each with a default assumption. Pending human review before sending.

## Suggestions rejected or changed

| Agent suggestion | Outcome |
|---|---|
| Custom repository layout | Changed to follow the brief's suggested shape |
| Defect inventory from reading generator code | Corrected by profiling the actual data (3 overstatements, 1 missed defect) |

## Verification

- Starter-pack SHA-256 checksums enforced by `tests/test_starter_data.py`.
- Agent claims about the data checked by profiling; the generator re-run to confirm it is the data source.
- External dataset codes and lags to be checked against provider sources.

## Remaining risks

- External indicators and metric definitions not yet decided; clarification answers pending.

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
