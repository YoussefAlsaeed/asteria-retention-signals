# Findings

> **Draft for human review.** Written from `data/curated/objective_measures.csv` and `association_results.csv` (run of 2026-09-28, as-of 2025-12-31). Metric definitions are confirmed by the clarification answers ([clarification_questions.md](clarification_questions.md)). Intervals are Wilson 95%. "Pooled" = hire years 2021–2024, the mature cohorts.

## 1. Senior-hire retention misses its target in every year, under either definition of "senior"

| Scope | Retained after 12 months | 95% CI | Target |
|---|---:|---|---:|
| Senior Leader (confirmed definition) | **78.6%** (209 / 266) | 73.3–83.1% | ≥ 90% |
| Senior Leader + Manager (sensitivity) | 81.0% (654 / 807) | 78.2–83.6% | ≥ 90% |

- Each mature hire year misses the target (73.9%, 78.9%, 80.6%, 81.0% for 2021–2024), and the whole interval sits below 90% (`confidence = clear`).
- Every country is below target (73.6% BG to 81.0% IT). Per-country samples are 35–55 hires, too small to rank countries reliably.
- **Decision relevance:** this is the largest and most robust gap. It uses the confirmed definition (Senior Leader only), and it would hold even if Managers were included.

## 2. New-hire six-month retention sits on the target, not clearly above it

- Pooled: **86.8%** (1,423 / 1,640), 95% CI 85.0–88.3%, against a target of ≥ 86%. Each mature year is "met", but every interval includes the target (`within_uncertainty`).
- Countries range from 84.7% (RO) to 89.2% (GR); all intervals overlap the target.
- Business units range from 85.1% (Sales) to 88.8% (Finance), but the ranking is **not stable** year to year (Supply Chain: 81.5% in 2021, 91.6% in 2022).
- **Decision relevance:** "met" should be read as "on the line". No country or unit is a reliable outlier, so targeted action by segment is not supported by this data.

## 3. Regretted turnover stays well inside the limit, but rose in 2025

| December, trailing 12 months | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| Regretted turnover | 4.3% | 3.7% | 3.3% | 3.3% | **5.1%** |
| Regretted exits | 23 | 32 | 38 | 46 | 82 |
| Mean month-end headcount | 537 | 858 | 1,143 | 1,407 | 1,610 |

- Company-wide it is below the ≤ 7.5% limit every year, clearly so (`confidence = clear`).
- In 2025, Romania (6.7%), Ireland (6.2%) and Bulgaria (6.1%) are the closest to the limit; their intervals include 7.5%.
- **Caveat:** nobody in the data was hired before 2020, so headcount grows from zero and the tenure mix shifts every year. Part of the 2025 rise may be compositional: more people are now past their first year. The cause is not identified.

## 4. Non-finding: no external signal is associated with any objective

- 15 within-country models (3 objectives × 5 signals). Each uses country fixed effects and a time trend, with standard errors clustered by country-month. **No association survives the false-discovery-rate correction** (every q ≥ 0.53).
- The single nominal result is **higher economic sentiment with fewer regretted exits**: odds ratio 0.82 per within-country SD, 95% CI 0.68–0.99, p = 0.04, q = 0.53. With 30 tests, about 1.5 results at p < 0.05 are expected by chance, so this is not evidence.
- **Confounding is visible:** for unemployment and regretted exits, the naive pooled odds ratio is 0.97, and it becomes 1.11 once countries are compared only with themselves. Pooling across countries mixes country differences with the signal.
- **Power is limited:** 57 senior early exits, 232 new-hire early exits, and 217 regretted exits across six countries and about five years. Only moderate-to-large effects could have been detected.
- **Not controlled for:** time since hire. Leaving is far more likely early in a job (2.4% a month in the first 6 months vs about 0.5% after 2 years), and the turnover model adjusts for country and a time trend but not for tenure. Next step: add tenure bands to the turnover model.
- **Would need:** more countries or employers, a longer history, individual-level drivers (pay, manager, role changes), and point-in-time vintages for all indicators, not only inflation.

## Data health and its effect on these findings

- The 2 voluntary exits with an unknown regretted flag move turnover by at most 0.12 points (upper-bound variant, 2022), so the effect is negligible.
- 10 records are excluded (blank hire date, or termination before hire), and 9 with no country appear only in company-wide figures. Neither changes a headline.
- Italy's vacancy rate has a different definition (Eurostat flag `d`). Within-country models are not affected by level differences, but cross-country vacancy comparisons are.
