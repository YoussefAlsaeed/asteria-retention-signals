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
7. **Generator disclosure (human insight).** The human noticed that the generator in the brief shows attrition is driven only by internal factors, not external data. The agent confirmed that the generator, re-run in Node, reproduces all three CSVs byte for byte. The human then argued the coefficients may themselves have been calibrated from external conditions. **Human decision: proceed blind.** The generator is not used in any analysis; external sources are pulled and relationships tested as the brief intends.
8. **Clarification questions (scope cut by human).** The agent drafted ten questions. The human cut them to the three that can change an objective result (senior scope, cohort scope and maturity, headcount denominator); the other seven became documented assumptions. Sent as [docs/clarification_questions.pdf](docs/clarification_questions.pdf). The agent also softened one PDF sentence that claimed an unverified effect on the 7.5% threshold.
9. **Source research (human search, agent fact-check).** The human used Claude web search to shortlist indicators. The agent verified every claim against the live APIs before accepting it:
   - **Confirmed:** all datasets exist and cover all six countries 2019 onward; `jvs_q_nace2` is frozen at 2025-Q4 with successor `jvs_q_r21`; `prc_hicp_manr` is frozen at 2025-12 with successor `prc_hicp_minr`; `prc_hicp_fpd` holds first-released values.
   - **Found by checking:** A-T vacancies missing for IE, EL, IT (B-T used instead); Ireland's GDP distorted by multinational accounting; Italy's sentiment missing 2020-04.
   - **Changed:** World Bank GDP demoted to annual context; Eurostat economic sentiment added as the primary cycle indicator. Accepted by the human.
   - **Agent's own errors caught:** two licence URLs recalled from memory were wrong (one 404, one redirect); replaced with pages verified to state CC BY 4.0.
   - Evidence links: [Eurostat copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice), [World Bank public licenses](https://datacatalog.worldbank.org/public-licenses), [Eurostat API guide](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/api), [World Bank API guide](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation), [une_rt_m](https://ec.europa.eu/eurostat/databrowser/view/une_rt_m/default/table), [jvs_q_r21](https://ec.europa.eu/eurostat/databrowser/view/jvs_q_r21/default/table), [prc_hicp_minr](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table), [prc_hicp_fpd](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_fpd/default/table), [ei_bssi_m_r2](https://ec.europa.eu/eurostat/databrowser/view/ei_bssi_m_r2/default/table), [NY.GDP.MKTP.KD.ZG](https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG). Full register: [docs/source_register.md](docs/source_register.md).
10. **Ingest layer.** The agent built config-driven adapters (Eurostat JSON-stat, World Bank), a retrying HTTP fetcher, a checksummed raw store, and per-indicator failure isolation, with 40 new tests. Verification: a live run followed by an idempotent re-run (all "unchanged") and an offline replay; two bugs were injected on purpose and each was caught by the tests. Failures fixed along the way: a wrong tenacity import and three strict-mypy type errors.
11. **Curate layer.** The agent wrote the transformations as SQL files run in DuckDB, with a catalogue of 23 quality rules whose severity decides each row's fate (corrected, warn, excluded, excluded from country views, or gate failure). Correction rules live in `config/workforce.yaml`; `Sr Mgmt` → Senior Leader follows the default assumption from clarification question 1. `asteria run` became the one-command core workflow.
   - **Verification:** every workforce count matches the independent pandas profile (7, 8, 9, 10, 5, 5, 13, 2, 90); external rows equal the ingest total (2,456); reruns are byte-identical; two SQL bugs were injected on purpose (future exits leaking in, a quarter treated as one month) and each was caught; the full suite passes on Python 3.11 as well as 3.13.
   - **Found in the data:** Eurostat flags every Italian vacancy quarter 2019–2025 as "definition differs". The label was read from the payload, not assumed, and is recorded in the source register.
   - **Agent failures:** the first version hung for over five minutes because row-by-row inserts commit per row on disk, so it was profiled step by step and the **human** suggested it to be replaced with one bulk insert (now about 5 s). The agent twice wrote Python 3.12-only generic syntax, despite the 3.11 target; both were fixed, and a rule was added to `CLAUDE.md`.
12. **Analyse layer (human: proceed on default assumptions, analysis blind).** The agent implemented the three objectives in SQL (monthly hire cohorts, calendar-month anniversaries, a maturity rule, trailing 12-month regretted turnover over the mean of month-end headcounts, and `GROUPING SETS` slices), point-in-time signals through a DuckDB `ASOF JOIN` with per-indicator publication lags, and person-level logistic models (country fixed effects, time trend, clustered errors, Benjamini-Hochberg correction).
   - **Verification:** the 2021 headline values were recomputed independently with pandas date offsets and match exactly (87.05%, 73.85%, 4.28%). The statistical method passed three known-answer tests on synthetic data: it detects a real effect, gives no false positive under the null, and is not fooled by country confounding that fools the naive model. Hand-computed boundary cases cover the anniversary day, immaturity, the manager sensitivity variant, and a 2020 hire in turnover. Two bugs were injected on purpose (anniversary exit counted as lost, publication lag ignored) and each was caught. Reruns are byte-identical, and the suite passes on Python 3.11.
   - **Bug found by the agent's own test:** in tiny slices, regretted exits can exceed the average headcount, and the Wilson interval then took the square root of a negative number. The interval is now undefined outside 0 ≤ k ≤ n, with a regression test.
   - **Agent self-correction:** the first quarter/year roll-up judged maturity from the hires present in a slice, which would have marked a sparse slice as mature too early. It was changed to period-level maturity before any result was used.
   - **Independent re-derivation (human request: "I need to verify your work"):** `scripts/verify_findings.py` recomputes every figure in the findings without importing pipeline code (pandas date offsets, `merge_asof` for the point-in-time join, statsmodels formula refits). 107 of 107 numbers agree. [docs/analysis_explained.md](docs/analysis_explained.md) explains the method for engineers.
   - **Findings:** the agent drafted [docs/findings.md](docs/findings.md) from the outputs; pending human review. The result is a non-finding for external signals (no q < 0.46).
13. **Methodology decisions returned to the human (human challenge).** The human pointed out they had not been consulted on the regression design or the publication lags. That was correct: the agent had made these choices itself, contrary to the rule in `CLAUDE.md` that methodology decisions belong to the human. The agent then produced a one-off walkthrough (not kept in the repository, at the human's request) that walked three real employees through every step and re-run all 15 tests under each alternative (join timing, calendar join vs lagged, extra lag, four control sets, clustering, three multiple-test corrections, and country-year correlation). No alternative changes the conclusion (smallest q = 0.15). The leaky calendar join gives the strongest-looking result, which illustrates why the lag rule exists.
   - **Agent claim corrected by this check:** first-release inflation had been called the most valuable safeguard, but 0 of 360 country-months were ever revised, so it makes no difference here.
   - **Human decision:** after reviewing the alternatives, the human confirmed all of the originally chosen options (as-of join at hire or month start, measured lags, country fixed effects plus trend, clustered errors, Benjamini-Hochberg, person-level unit).

14. **API and dashboard.** The agent built a FastAPI read-only API (repository with parameterised SQL, typed response models, input validation that lists allowed values, and one error contract: 404, 422, 503 "not built" with the fix, and 500 with a request id but no internals) and a dependency-free HTML/SVG dashboard covering the brief's Explore, Understand, Challenge, and Trust views. The colour palette was validated with the dataviz skill's colour-blind checker, not by eye.
   - **Verification:** 16 API tests and 11 browser tests (Playwright) cover loading, filters and URL state, empty and pending states, API unreachable with retry, "data not built", keyboard reading of charts, table views, and an axe accessibility audit in both themes. The agent screenshotted and inspected the page; it broke the error banner on purpose, and the tests caught it.
   - **Bugs found by the agent's own checks:** a SQL `ORDER BY` outside `GROUP BY ALL` made two endpoints fail with 500, and the 500 contract hid the internals as designed while the log showed the cause. Legends rendered the text "null". Tables were clipped. Provider flags came out in a non-deterministic order.
   - **Accessibility failures caught by axe:** links and summaries used the chart's series blue as text (4.3:1, below WCAG AA and against the palette rule that text never wears the series colour), and the dark-mode status badges reached only 4.2:1. Both were replaced with computed colours of at least 5.2:1. Scrollable table views were not keyboard-reachable; they are now focusable, named regions.
   - **Restyle (human request):** the dashboard now matches the assessment brief's visual language (navy topbar, teal accents, numbered section cards) and uses the full page width. The palette was re-validated against the new surfaces, and all text contrast recomputed (at least 4.6:1). The tests caught two regressions the restyle introduced: a newly scrollable table without keyboard access, and a badge test reading CSS-uppercased text instead of the DOM text a screen reader gets.
15. **Readable logs (human feedback).** The human found JSON logs hard to read in the terminal. Logs are now text by default in an interactive terminal (warnings and errors only, since the CLI prints its own summaries) and JSON at INFO when output is piped or captured, which keeps machine-readable observability for production. Formatter selection and levels are covered by tests.

16. **Publication-lag spot check (human request).** The human asked how the lags were derived; the agent explained they came from a single snapshot's "last updated" dates, which is only a proxy. At the human's request the agent checked them against official release dates for 2021–2026 (Eurostat news releases, the DG ECFIN survey archive, the World Bank WDI update log). **Finding: the agent's 0-day lag for economic sentiment leaked**, because December surveys are published 5–8 January but were used from 1 January (4,861 person-months, 145 cohort members). The inflation lag was also shorter than January releases (22–24 days), though no value was used early. **Human decisions:** sentiment lag raised to 10 days, inflation lag to 25. Re-run: the conclusion is unchanged (smallest q 0.53), and the independent verification agrees 107/107. Every date and source is listed in the source register.

17. **Making the findings legible (human feedback).** The human found the dashboard's findings hard to follow and did not understand "not assessed". The agent diagnosed two causes. First, the findings pool 2021–2024 while the dashboard showed only single years. Second, filtered slices quickly fall below the 30-person minimum: 97% of senior country-year slices do (5–19 senior hires a year per country). **Human decisions:** add a Key findings panel with "Show me" presets, and clearer small-sample cards. Keep pooling to complete years; the alternative that adds January–June 2025 hires was offered and declined. The panel's numbers come from a new `/api/findings` endpoint, not typed text, and tests pin them to the documented headlines. The screenshot review also caught a rounding trap (7.52% displayed as "7.5%, not met" against a 7.5% limit), now shown to two decimals. Also added: a dashboard guide and a data-to-conclusion diagram for the presentation. The human then could not see the new buttons: the browser was serving a cached old `app.js`, because the static files had no cache policy. Dashboard files are now sent with `Cache-Control: no-cache` (revalidated via ETag), with a test.

18. **Presentation, architecture view, and a numbers walkthrough (human request).** The agent built a 15-slide HTML deck (`presentation/deck.html`, exported to `deck.pdf`) following the brief's 3/5/4/3-minute structure, with speaker notes. It wrote the production architecture mapping (`docs/architecture.md`: ADF, Databricks, Power BI; secrets, scheduling, observability, storage, access control, promotion), labelled as a proposal, not built. It rewrote `docs/analysis_explained.md` as a walkthrough of every number, with hand calculations. **Verification:** every quoted figure was pulled from the data, not recalled. The Wilson interval was computed by hand (209/266 → 73.3–83.1%) and matches the pipeline. The model row count reconciles (1,640 − 4 + 172 = 1,808). Each slide was rendered and checked for overflow, which caught a sticky header in a screenshot, clipped content, and a CSS specificity bug. One slide claim was softened because the robustness alternatives were run before the lag fix. The effort estimate is left for the human to fill in.

19. **Scope of the external-signal test (human question).** The human asked why signals are tested per objective rather than against all leavers. The agent explained two things: leavers-only analysis has no comparison group, and different kinds of leaving can react to the economy in opposite directions. As an exploratory check (outside the pipeline) it pooled all exits. That first showed apparent links: unemployment OR 1.20, q 0.012; vacancies OR 0.85, q 0.002. Both pointed the wrong way, and adding time since hire and year baselines removed most of them (voluntary exits: p 0.19–0.21). **Human decisions:** keep the official models as they are, with tenure documented as a limitation and next step, and leave the all-leavers check out of the analysis. The human then asked for plain-language explanations in the deck: two new slides ("Reading the numbers" and "The economic question, in plain words") and "In plain words" lines on the technical slides; 17 slides, with no overflow on any.

20. **Clarification answers received.** All three confirmed the implemented definitions: Senior Leader only with Sr Mgmt normalised; hires from 2021 included only when hire + N months ≤ 31 Dec 2025; mean of the 12 month-end headcounts. The agent checked the one wording difference, a per-person maturity rule vs the implemented per-cohort rule, on the real data: 0 disagreements (1,813 and 266 people), because the data ends on a month end. A test now pins this. No number changed. The label "Pending" was renamed to the answer's term, "Not yet observable"; the internal status code is unchanged. Docs, deck and diagram now say "confirmed" instead of "assumption".

21. **Dashboard shows the confirmed definition only (human decision).** With the definitions confirmed, the human removed the Definition filter. The dashboard now always shows the main definition, and Finding 1's card no longer quotes the Senior + Manager figure. The sensitivity variants remain in the analytical tables and the written findings as robustness evidence. The agent's edit left a dangling `+` that broke the page. The browser tests caught it (14 failures). It had slipped past `node --check` because the file was checked as a classic script, not as the ES module the browser loads; checks now use `.mjs`.

22. **API package structure (human request).** The human asked for the API to be organised into packages rather than one file. The agent split it: `routers/` (one module per resource), `repository/` (a base connection plus objective, signal and trust query groups, combined in one `Repository`), `schemas/` (models grouped the same way), `services/` (meta, findings summary, method definitions), plus `dependencies`, `errors` and `middleware`. Validation moved into FastAPI dependencies (`ObjectiveDep`, `CountryDep`, and so on), which removed every `# type: ignore` in the routes. The significance threshold is now a named constant. **Verification:** the OpenAPI surface is identical (the same 9 endpoints and parameters); all 129 tests pass on Python 3.13 and 3.11; strict mypy and ruff are clean; no module is longer than 96 lines (the old `app.py` was 289).

23. **Person-months slide (human request).** After an explanation of person-months, the human asked for it in the deck. The agent added an optional slide with one real employee's rows (May excluded, June–October included), the 65,184 / 217 / 0.33% totals, and the one-row-per-hire contrast for the hire targets. 18 slides, with no overflow on any; PDF rebuilt.

24. **Production-mapping slide removed (human decision).** The human removed the ADF / Databricks / Power BI slide from the deck. It was agent-drafted, and the human had not had time to research it enough to present it. The brief's production-architecture requirement is still met by `docs/architecture.md`, which now states that it is an agent-drafted proposal, not validated against a real Azure environment. Deck: 17 slides.

25. **"Inside the model" slide (human-written explanation).** The human wrote a plain-language, step-by-step account of the logistic regression (inputs → b → odds ratio → 95% range → p → q) and asked for it in the deck. The agent laid it out as an optional slide after person-months and kept the human's full wording in the speaker notes. **Changed:** "18% lower odds" now says it is per one step of the signal (5.78 sentiment points), because the model scales the signal by its within-country SD. **Verification:** the numbers were checked against the association output (b −0.2015, OR 0.82, 0.68–0.99, p 0.035, q 0.53); 18 slides, with no overflow; PDF rebuilt.

## Suggestions rejected or changed

| Agent suggestion | Outcome |
|---|---|
| Custom repository layout | Changed to follow the brief's suggested shape |
| Ten clarification questions | Cut to three critical ones by the human |
| Defect inventory from reading generator code | Corrected by profiling the actual data (3 overstatements, 1 missed defect) |
| World Bank GDP as the cycle indicator (from the human's search) | Demoted to annual context after the Ireland distortion was found; sentiment added |
| Licence URLs recalled from memory | Two were wrong; replaced with verified pages |
| Methodology choices made without the human | Returned for decision with every alternative re-run |
| "First-release inflation is the key safeguard" | Wrong: HICP had 0 revisions in 2021–2025 |
| Lags estimated from one snapshot (sentiment 0 days) | Spot check found a December leak; human chose a 10-day lag |

## Verification

- Starter-pack SHA-256 checksums enforced by `tests/test_starter_data.py`.
- Agent claims about the data checked by profiling; the generator re-run to confirm it is the data source.
- Dataset codes, coverage, and licences checked against live provider APIs and terms pages.
- Ingest and curate tests validated by deliberately injecting bugs and confirming the tests fail.
- Curated counts reconciled against an independent profiling script; reruns byte-identical; tests run on Python 3.11.
- Objective headlines recomputed independently; association method validated on synthetic data with known answers.

## Remaining risks

- Metric definitions are confirmed by the clarification answers (received 2026-09-30).
- Publication lags are estimated from one observation date and applied to all history.
- The workforce has no pre-2020 employees, so turnover trends mix real change with tenure composition.
- `prc_hicp_fpd` release semantics (FIN vs FLS) inferred from data, not yet confirmed in Eurostat metadata.
- Only inflation has first-release values; the other indicators carry revised values (look-ahead risk).
- Italy's job vacancy rate follows a different definition (Eurostat flag `d`); cross-country vacancy comparisons that include Italy need a caveat.

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
