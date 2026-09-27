# CLAUDE.md

Rules for working in this repository. Source of truth: [docs/assessment_brief.html](docs/assessment_brief.html). If a rule here conflicts with the brief, the brief wins; fix this file.

## Context

- Assessment: "External signals × workforce retention" for Asteria Consumer Products (fictional; 6 markets: GR, RO, PL, IT, IE, BG).
- Track: **software emphasis**. The complete vertical slice is still required: reviewers expect a reliable data path and defensible analysis, not only good code.
- Workforce horizon 2021–2025, as-of date **2025-12-31**. Seed 20260831. All data is synthetic.
- Business outcome: a trustworthy view of retention performance and the external conditions that may contextualise it. Engineering outcome: a reproducible, inspectable path from source research through ingestion, transformation, features, quality, and insight delivery.
- Graded on 8 dimensions: problem framing, source research, ingestion, data modelling, analysis, insight product, engineering, agentic practice.

## 1. Problem framing comes first

- Refine the problem before building: the decision being supported, metric semantics, data grain, temporal alignment, assumptions. Good narrowing is graded.
- Record questions, assumptions, metric definitions, acceptance criteria, decisions, rejected scope, and consequences in `docs/` (requirements refinement).
- **Implementation depth matters more than surface area.** Build one coherent vertical slice: Research → Ingest → Curate → Analyse → Explain.
- Make tradeoffs explicit. Keep the core path runnable at all times. A deliberate cut beats an unfinished broad feature; if a feature is cut, preserve a runnable core and document the next step.

## 2. Starter data

- Starter files live in `data/raw-or-fixtures/starter/` and are **evidence**: never edit them. Their bytes must match `assessment_data_manifest.json` (enforced by `tests/test_starter_data.py`; `.gitattributes` keeps them byte-exact).
- The data is intentionally imperfect. **Do not assume blanks are errors, or that populated values are valid.** Profile before trusting.
- Recent hires may not have completed an objective's observation window: treat them as censored, not as retained.
- Canonicalise country codes before joining (`EL` is Eurostat's code for Greece; `ROM` is a Romania alias). Every exclusion or correction must be counted and reported, never silent.
- The brief's embedded JavaScript generator reproduces the starter CSVs exactly. Attrition in it depends only on internal factors (country, hire year, business unit, level, contract type), never on external data. **Never use the formula as an analysis input or tune results to it.** Disclose it openly, use it only to sanity-check that the pipeline recovers known internal effects, and treat every external association as non-causal.

## 3. Retention objectives

Produce **auditable** measures for all three objectives (`retention_objectives.csv`). For each, make explicit: cohort eligibility, denominator, boundary dates, censoring, and treatment of invalid records.

| Objective | Target | Must document |
|---|---|---|
| `NEW_HIRE_6M` | ≥ 0.86 | A defensible cohort definition; incomplete observation windows |
| `SENIOR_HIRE_12M` | ≥ 0.90 | Which career levels qualify; how cohort maturity is determined |
| `REGRETTED_TURNOVER_12M` | ≤ 0.075 | The denominator and the average-headcount convention |

Objectives are effective 2021-01-01 to 2025-12-31.

## 4. External sources

- At least **two authoritative public providers**, at least **three relevant indicators**, about **three years** of history where the source supports it.
- Indicators must cover at least **two lenses**: labour supply, labour demand, cost-of-living pressure, economic cycle, or workforce structure. Justify each choice.
- Examples, not prescriptions: Eurostat, World Bank, OECD, ILOSTAT, national statistical offices.
- For every source, document in the source register: URL, licence or terms, cadence, scope/coverage, access date, definitions, units, dimensions, publication lag, canonical mapping, known limitations.
- **Never treat an agent-generated citation, dataset code, schema, or statistic as fact** until checked against the provider.

## 5. Data layers and contracts

- Preserve raw source payloads, or faithful replay fixtures, so review works without a network.
- Keep **source-shaped** and **canonical** records separate.
- Expose a **consumption-ready analytical product**.
- Every record retains lineage: source, indicator, unit, frequency, period, load time, and quality status.
- Canonical countries, periods, units, dimensions, quality, freshness.

## 6. Reliability

- **One documented command** runs the core workflow.
- Deterministic reruns; intentional overwrite/upsert behaviour (idempotent).
- Useful failure messages; safe handling of partial failures (one source failing must not corrupt the others).
- Re-runnable retrieval with raw evidence, failure handling, and source metadata.
- Tests cover the **riskiest** assumptions and transformations: parsing, mapping, metric, quality, and temporal rules. Tests must be fast, repeatable, and network-independent.

## 7. Temporal alignment and frequency integrity (non-negotiable)

- Join workforce outcomes to external signals **without future information**: respect publication lag, not only the reference period.
- Document period semantics, mixed frequencies, and why each aggregation or as-of rule was chosen.
- **Never present an annual observation as twelve newly measured monthly values.** If a value is carried forward for an as-of use, preserve its original period, publication status, and age, and explain the rule.

## 8. Analysis and insight

- Evaluate relationships with an appropriate descriptive or statistical method.
- Make explicit: sample size, uncertainty, repeated observations, confounding, multiple comparisons, and **why correlation is not causation**.
- Deliver **at least three evidence-backed findings** and **at least one limitation or non-finding**.
- For each finding: decision relevance, segment stability, data-health impact, and what further evidence would be needed.

## 9. Dashboard (interactive insight experience)

A runnable local dashboard or equivalent interactive report with:

- **Explore:** filters for country, time, retention objective, and at least one workforce segment.
- **Understand:** retention trends and objective status alongside selected external signals.
- **Challenge:** relationship views showing sample size or uncertainty, plus honest caveats.
- **Trust:** data freshness, coverage, quality exclusions, source attribution, methodology.

## 10. Software-emphasis depth

- Clear **adapters**, **domain boundaries**, and **configuration**. Domain logic has no I/O; each provider sits behind a common adapter interface; settings live in `config/`, not in code.
- **Resilient API handling** (timeouts, retries, clear error types) and **observable failures** (structured logs, run manifest).
- **Packaging, dependency management, developer experience:** uv, `pyproject.toml`, locked dependencies, clear commands.
- **Automated tests across service and UI boundaries** (unit, contract, API, UI).
- **Accessible dashboard interaction** and **graceful empty/error states**.

## 11. Stack constraints

- Python 3.11+. Demonstrate SQL concepts. pandas or local PySpark for processing.
- Experience layer: Power BI Desktop or HTML.
- **No paid infrastructure requirements.**
- Include one **production architecture view** mapping the solution to ADF-style orchestration, a Databricks/lakehouse environment, and Power BI consumption. It must address secrets, scheduling, observability, storage, access control, and promotion between environments.

## 12. Deliverables (definition of done)

| Artifact | Required content |
|---|---|
| `README.md` | Problem, chosen scope, architecture, prerequisites, one-command core run, dashboard run, tests, outputs, known limitations |
| Requirements refinement | Questions, assumptions, metric definitions, acceptance criteria, decisions, rejected scope, consequences |
| Source register and contracts | Provider evidence, licensing/terms, indicators, units, dimensions, cadence, lag, canonical mapping, limitations |
| Implementation | Ingestion, layered transformations, quality controls, retention features, temporal integration, analysis, dashboard |
| Tests and fixtures | Fast checks for highest-risk parsing, mapping, metric, quality, temporal rules; replay data for offline review |
| Generated evidence | Representative curated data, quality/coverage report, analytical output, screenshots or export, source attribution |
| `AI_USAGE.md` | Tools/models, meaningful prompts or task descriptions, accepted and rejected suggestions, human validation, failures, remaining risk. **No secrets, no full transcripts.** |
| Presentation | Lightweight PDF, HTML, or Markdown deck for the 15-minute presentation |

Also: submit as a public repository, or grant reviewers private access, by the recruiter's deadline. State approximate effort honestly. One concise batch of clarification questions is allowed; if unanswered, record a reasonable assumption and proceed.

## 13. Agentic practice (AI accountability)

- **Update `AI_USAGE.md` at the end of every meaningful session**: what the agent did, what was accepted, rejected or changed, how it was verified, failures, remaining risk. Keep it brief.
- Show: how work was decomposed and scope controlled; which tasks the agent did and which decisions stayed human; at least one rejected or materially changed suggestion; how tests, source evidence, and inspection verified outputs.
- Do not produce code or analysis the human cannot explain. Prefer clear, simple code over clever code.
- Do not send sensitive information to an AI service.
- Do not hide material failures or manual corrections; log them.
- Decisions on metric definitions, scope, indicators, and findings belong to the human. Propose options with a recommendation, then wait.

## 14. Final interview (keep the work presentable)

- 15-minute presentation: 3 min problem refinement and scope, 5 min architecture/lineage/reliability, 4 min dashboard and key findings, 3 min tradeoffs/AI usage/next steps.
- Followed by 15 minutes of technical Q&A: expect to navigate the code live and change reasoning when challenged. Code must be easy to find and explain.

## Repository conventions

- Layout follows the brief's suggested shape: `README · docs/ · src/ · tests/ · data/raw-or-fixtures/ · data/curated/ · dashboard/ · presentation/ · AI_USAGE.md`, plus `config/`.
- Commands: `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run asteria --help`.
- Git: commit as Youssef Alsaeed <yousefalsaeed2002@gmail.com>; push to `YoussefAlsaeed/asteria-retention-signals` (private). This repo's credential helper uses `gh auth git-credential`.
