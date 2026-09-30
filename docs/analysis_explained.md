# How every number was produced: a walkthrough for developers

This walks through the whole analysis in plain terms: what goes in, what each step computes, where the code is, and how each headline number is calculated by hand. No statistics background is assumed.

Reproduce and check everything:

```sh
uv run asteria run                        # rebuild all numbers from the committed inputs (offline)
uv run python scripts/verify_findings.py  # recompute every finding with separate code: 107 / 107 agree
```

---

## 1. The chain in one table

| Step | Input | What happens | Output | Code |
|---|---|---|---|---|
| Ingest | 5 public data series via API | Download, contract check, store the exact bytes | 6 raw snapshots (5 signals + revised inflation for comparison) | `src/asteria/sources/`, `src/asteria/ingest/` |
| Curate: employees | 2,407 CSV rows | Deduplicate, fix codes, apply 23 quality rules | **2,400 people**; **2,390 measurable**; 2,381 with a known country | `src/asteria/curate/sql/workforce.sql` |
| Curate: external | Raw snapshots | Map countries, turn periods into real dates, check gaps | **2,456 values** | `src/asteria/curate/sql/external.sql` |
| Measure targets | Clean employees | Cohorts, anniversaries, headcounts, 95% intervals | `mart_objective_measures` | `src/asteria/analytics/sql/retention.sql` |
| Time-safe join | Clean external values | "What was known on the 1st of each month" | `mart_signal_asof` | `src/asteria/analytics/sql/signals.sql` |
| Test for links | Targets per person + signals | 30 logistic models; multiple-test correction | `mart_association_results` | `src/asteria/analytics/association.py` |
| Show | All `mart_*` tables | API + dashboard | Dashboard | `src/asteria/api/`, `dashboard/` |

**Findings 1–3 use only the employee path. Finding 4 is where the two paths meet.**

---

## 2. The employee data

One row per person. What cleaning did (full list in `data/curated/quality_report.md`):

| Step | Rows | Result |
|---|---:|---|
| Rows in the CSV | 2,407 | |
| Exact duplicate rows removed | −7 | **2,400 people** |
| Excluded from every calculation (no hire date: 5; left before being hired: 5) | −10 | **2,390 measurable** (`is_measurable = true`) |
| No country: counted company-wide, left out of country views | 9 | **2,381 in country scope** (`in_country_scope = true`) |
| Corrected, not removed: `EL`/`ROM` → GR/RO (8); "Sr Mgmt" → Senior Leader (10) | 18 | kept |

Each person in `data/curated/employees.csv` has a `quality_rules` column listing every rule that touched them.

---

## 3. Targets 1 and 2: "of the people hired, how many were still here N months later?"

### The rule

```python
anniversary = hire_date + N calendar months   # 31 Jan + 6 months = 31 Jul; 31 Aug + 6 = 28/29 Feb
lost        = exit_date is not None and exit_date < anniversary   # leaving ON the anniversary = stayed
retention   = count(not lost) / count(hired)
```

- **Cohort:** everyone hired in the same calendar month. Months are then added up into quarters and years.
- **Pending:** a period is only reported once *every* hire in it has reached the anniversary by 31 Dec 2025. Otherwise the rate is left empty and the status is `pending`. Counting unfinished hires as "stayed" would inflate retention.
- **Code:** `retention.sql`
  - `mart_cohort_members` (line 33): one row per eligible hire, with `lost` and `cohort_mature`
  - `cohort_monthly` (line 55): monthly counts per country and business-unit slice
  - `cohort_measures` (line 77): quarter and year roll-ups, and maturity

### Worked example: senior hires in 2024 (the Status card "81.0%")

- **63** Senior Leaders were hired in 2024. That's the **denominator**.
- **12** of them left before their 12-month anniversary, so **51** stayed. That's the **numerator**.
- **Rate** = 51 ÷ 63 = 0.8095 → **81.0%**.

### Worked example: the pooled finding "78.6%"

The finding adds up the complete years (2025 is still pending):

| Hire year | Stayed (numerator) | Hired (denominator) | Rate |
|---|---:|---:|---:|
| 2021 | 48 | 65 | 73.8% |
| 2022 | 56 | 71 | 78.9% |
| 2023 | 54 | 67 | 80.6% |
| 2024 | 51 | 63 | 81.0% |
| **Total** | **209** | **266** | **209 ÷ 266 = 78.6%** |

It adds counts, not percentages. Averaging the four percentages would give big and small years equal weight.

### "Main" vs "Senior + Manager"

The brief doesn't say which career levels count as "senior", so we asked, and in the meantime we compute both:

| Definition | Who counts as senior | Pooled 2021–2024 |
|---|---|---|
| **Main** (our assumption) | Senior Leader, including the 10 "Sr Mgmt" rows mapped to it | **209 / 266 = 78.6%** |
| **Senior + Manager** (sensitivity check) | Senior Leader **and** Manager | **654 / 807 = 81.0%** (yearly 83.8, 81.2, 77.8, 81.2%) |

Both are clearly below 90%, so **finding 1 doesn't depend on the answer**. That's why we show the second definition: it proves the assumption doesn't drive the conclusion. In the config (`config/analysis.yaml`) this is `levels` vs `sensitivity_levels`.

### New hires (the "86.8%")

It's the same rule with 6 months and every career level: 1,423 stayed out of 1,640 hired in 2021–2024, which gives **86.8%**.

---

## 4. Target 3: regretted turnover

The definition you asked about, phrase by phrase:

> *"Regretted exits in the trailing 12 months divided by the mean of the 12 month-end headcounts in that window. Unknown regretted flags count as not regretted (an upper-bound variant counts them as regretted)."*

| Phrase | Meaning |
|---|---|
| **Regretted exits** | People who **quit voluntarily** *and* whom the company marked as a loss (`regretted_exit = true`). Dismissals and contract ends are never "regretted". |
| **In the trailing 12 months** | A sliding 12-month window. The "2025" value covers exits from 1 Jan to 31 Dec 2025; the "March 2025" monthly value covers April 2024 to March 2025. |
| **Mean of the 12 month-end headcounts** | Count the workforce on the last day of each of the 12 months, then average the 12 numbers. It's the "typical workforce size" during the window. The workforce grew a lot, so the start or end alone would be misleading. |
| **Unknown regretted flags** | 2 people quit voluntarily but their regretted field is blank: one in Bulgaria (Nov 2024), one in Ireland (Jan 2022) |
| **Count as not regretted / upper-bound variant** | *Main* treats them as not regretted. *Unknown regrets counted* (the Definition filter) treats them as regretted. That changes 2022 from 32 to 33 exits (3.73% → 3.85%) and 2024 from 46 to 47 (3.27% → 3.34%). The verdict is the same either way. |

### Worked example: 2025 = 5.1%

**Headcount** on each month end in 2025 (hired on or before that day and not yet left):

| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,535 | 1,554 | 1,567 | 1,586 | 1,604 | 1,607 | 1,629 | 1,640 | 1,652 | 1,664 | 1,661 | 1,617 |

- **Average headcount** = sum 19,316 ÷ 12 = **1,609.7**. That's the **denominator**.
- **Regretted exits** with an exit date in 2025: **82**. That's the **numerator**.
- **Rate** = 82 ÷ 1,609.7 = **5.09%**, shown as 5.1% against the limit of 7.5%.

**Code:** `retention.sql`, `turnover_monthly` (line 129). It uses SQL **window functions**: `sum(...) OVER (… ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)` gives the 12-month sums and averages. `turnover_measures` (line 192) picks December for the yearly values.

---

## 5. Reading the data tables

The "Show data table" views and `data/curated/objective_measures.csv` have these columns:

| Column | Meaning | Example (senior 2024) |
|---|---|---|
| `numerator` | Cohorts: hires who stayed. Turnover: regretted exits. | 51 |
| `denominator` | Cohorts: hires. Turnover: average month-end headcount. | 63 |
| `rate` | numerator ÷ denominator (empty if pending) | 0.8095 |
| `ci_low`, `ci_high` | The 95% interval (next section) | 0.696 – 0.888 |
| `status` | `met` / `not_met` / `pending` / `insufficient_sample` (under 30 people) | not_met |
| `confidence` | `clear` = the whole interval is on one side of the target; `within_uncertainty` = it includes the target | clear |
| `variant` | `main` or a sensitivity definition | main |
| `grain` | month / quarter / year | year |

---

## 6. The 95% interval: "how sure are we?"

**The idea:** if 51 of 63 senior hires stayed, the "true" underlying rate isn't necessarily exactly 81.0%. With a different random set of 63 people, you might have seen 48 or 55. The 95% interval is the range of true rates consistent with what we observed: **69.6% to 88.8%** for this card.

- **With few people:** 3 hires gives an enormous interval that's useless for judging, hence the 30-person minimum.
- **With many people:** 1,640 hires gives a narrow interval (85.0–88.3%).
- **How to read it against a target:**
  - **"Clearly" missed or met:** the whole range is on one side of the target.
  - **"On the line":** the range includes the target, so the verdict could flip by chance.

**The formula** (Wilson score interval, the standard for a share of people). It's better than the simple "± 2 standard errors", which misbehaves near 0% or 100%. Worked for the pooled senior figure (k = 209 stayed, n = 266 hired, z = 1.96 for 95%):

```
p̂      = k / n                                  = 209 / 266          = 0.7857
centre = (p̂ + z²/2n) / (1 + z²/n)               = 0.79293 / 1.01444  = 0.7816
margin = z·√(p̂(1−p̂)/n + z²/4n²) / (1 + z²/n)    = 1.96 × 0.02543 / 1.01444 = 0.0491
interval = centre ± margin                       = 0.7325 to 0.8308  →  73.3% – 83.1%
```

Even the top of the range (83.1%) is below 90%, so the verdict is **clearly missed**.

**Code:** the `wilson_low` / `wilson_high` SQL macros at `retention.sql` lines 15–22. They return nothing when the numerator exceeds the denominator, which can happen for turnover in tiny slices (for example 1 exit against an average headcount of 0.17). That case once crashed the calculation, and a test now covers it.

---

## 7. The external signals and what "known at the time" means

| Signal | Plain meaning | Unit | Frequency | Lag used |
|---|---|---|---|---:|
| Unemployment rate | % of people who want work but have none | % of labour force | monthly | 62 days |
| Job vacancy rate | % of jobs open and unfilled | % of posts | quarterly | 90 days |
| Inflation (first release) | Price rise vs a year earlier, as first announced | % | monthly | 25 days |
| Economic sentiment | Survey of business and consumer confidence | index, 100 = long-run average | monthly | 10 days |
| GDP growth | How much the economy grew that year | % | annual | 200 days |

**Lag** is how long after a period ends before its number is treated as public. It's set conservatively and checked against official release dates (see the source register).

**The rule:** for every country and every 1st of the month, take the **latest value whose `period_end + lag` is on or before that date**. What Greece "knew" on 1 June 2023:

| Signal | Value used | Describes | Age |
|---|---:|---|---:|
| Economic sentiment | 108.0 | April 2023 (May's came out 30 May; the 10-day rule waits) | 32 days |
| Inflation | 4.5 | April 2023 | 32 days |
| Unemployment | 11.4 | March 2023 | 62 days |
| Job vacancies | 0.9 | Q4 2022 | 152 days |
| GDP growth | 8.7 | **year 2021** (2022 not yet published) | 517 days |

These are the "signal numbers" on the dashboard's right-hand chart (a step line: the value stays until the next publication), and the inputs to the models. **Code:** `signals.sql`: `mart_signal_values` (line 12) adds `available_from`, and `mart_signal_asof` (line 28) uses a DuckDB `ASOF JOIN`, which picks the latest row at or before a date.

---

## 8. The logistic regression: what it is, where it is, what it was fitted on

### What question it answers

*"When a signal was higher than usual in a country, were people in that country more or less likely to leave?"* It **doesn't predict** anyone's future. It tests whether a link exists at all. That's also why there is **no train/test split**: a split is for checking predictions on unseen data. Here the model is fitted once on **all** rows, and the output we care about is one coefficient and its uncertainty.

### Where the code is

| Step | File and line |
|---|---|
| Build the input table (SQL) | `src/asteria/analytics/pipeline.py`, `_model_frame` (line 148) |
| Loop over 3 targets × 5 signals, then correct for multiple tests | `src/asteria/analytics/association.py`, `fit_associations` (line 59) |
| Prepare one model: scale the signal, add trend, country columns, clusters | same file, `_fit_pair` (line 73) |
| Fit it with statsmodels `GLM(family=Binomial)` | same file, `_logit` (line 115) |
| Independent re-implementation (checks the above) | `scripts/verify_findings.py` |

### What it was fitted on: the input rows

**For the hire targets, one row per hire** (in a country, in a completed cohort):

| employee | country | as-of date (hire month) | event: left early? | sentiment known then |
|---|---|---|---:|---:|
| ACP001527 | GR | 2023-01-01 | 0 | value known on 1 Jan 2023 |
| ACP001118 | GR | 2023-05-01 | **1** (left 2 Oct 2023, before 2 Nov) | value known on 1 May 2023 |

**For turnover, one row per person per month employed ("person-month")**, so the signal can change month by month. ACP001118:

| month | event: regretted exit this month? | sentiment used | describes |
|---|---:|---:|---|
| 2023-06 | 0 | 108.0 | Apr 2023 |
| 2023-07 | 0 | 107.1 | May 2023 |
| 2023-08 | 0 | 109.0 | Jun 2023 |
| 2023-09 | 0 | 110.1 | Jul 2023 |
| 2023-10 | 0 (quit, but not regretted) | 110.7 | Aug 2023 |

| Model family | Rows | "Events" (1s) | Groups for errors |
|---|---:|---:|---:|
| New hires, 6 months | 1,808 hires | 232 left early | 322 country-months |
| Senior hires, 12 months | 266 hires | 57 left early | 171 country-months |
| Regretted turnover | 65,184 person-months | 217 regretted exits | 360 country-months (6 × 60) |

The new-hire model has 1,808 rows, not the finding's 1,640: it adds the **172 January–June 2025** hires (their 6 months are complete) and leaves out the **4** hires with no country, which can't be matched to a country's signal. 1,640 − 4 + 172 = 1,808.

### The model, in one line

```
chance of leaving  ↔  signal (in "steps")  +  a separate baseline for each country  +  a straight-line time trend
```

| Input | Plain meaning | Why it's there |
|---|---|---|
| **event** (0/1) | Left early / regretted exit that month | What we explain |
| **x** = signal ÷ one "step" | The signal value, measured in typical within-country swings | So the five signals are comparable |
| **country columns** (5 yes/no columns; Bulgaria is the reference) | Each country gets its own baseline level | Greece is only compared with Greece. Removes culture, law, pay and other country differences. |
| **trend** (months since Jan 2021) | A steady drift over time | Stops "both went up over 2021–2025" looking like a link |

**One step** (the within-country standard deviation) is how much a signal typically moves within a country. In the turnover model it's 5.8 sentiment points, 1.24 points of unemployment, 0.38 points of vacancy rate, 3.9 points of inflation and 4.9 points of GDP growth.

### What comes out: the odds ratio (OR)

The model returns one number for the signal. Turned into an **odds ratio**:
- **OR = 1.00:** the signal makes no difference.
- **OR = 0.82:** one step up goes with **18% lower odds** of leaving.
- **OR = 1.17:** one step up goes with 17% higher odds.

**The strongest result:** economic sentiment × regretted turnover gives OR **0.82** (95% range 0.68–0.99, p 0.035). In plain numbers:
- The average chance of a regretted exit in any month is 217 ÷ 65,184 = **0.33%**.
- The model says that when sentiment is one step (5.8 points) higher than usual in that country, it's about **0.27%**.

**"Naive" vs "within country":**

| Model | Sentiment × turnover | Unemployment × turnover |
|---|---|---|
| Naive (no country baselines, no trend) | 0.87 | 0.97 |
| Within country (the one we trust) | 0.82 | **1.11** |

The unemployment result **flips direction** once each country is compared only with itself. That shows how pooling countries mixes "which country" with "what the economy did".

**Why errors are clustered by country-month:** everyone in Greece in March 2023 shares the same signal value. So 40 people there are **one** observation of the economy, not 40. Clustering stops the model from being overconfident about that.

---

## 9. p and q: "could this be luck?"

**p-value:** assume the signal has *no* effect at all. p is the chance of seeing a result at least as strong as ours anyway. Small p (under 0.05, a 1-in-20 chance) is the usual bar for "probably not luck". The sentiment result has **p = 0.035**, just under the bar.

**The catch:** we ran **15** such tests. With 15 tries, getting at least one p under 0.05 by pure luck is likely, like rerunning a flaky test until it passes once. So each p must be adjusted for how many tests were run.

**q-value (Benjamini-Hochberg):** the adjusted version. The recipe:
1. Sort the 15 p-values from smallest to largest.
2. For each one, compute **p × 15 ÷ its rank**.
3. Going from the largest down, take the running minimum, so q never decreases.

| Rank | Test | p | p × 15 ÷ rank | q |
|---:|---|---:|---:|---:|
| 1 | Turnover × economic sentiment | 0.0353 | 0.0353 × 15 ÷ 1 = **0.53** | **0.53** |
| 2 | Turnover × GDP growth | 0.0862 | 0.65 | 0.65 |
| 3 | Turnover × inflation | 0.1540 | 0.77 | 0.77 |
| 4 | Senior × economic sentiment | 0.2662 | 1.00 | 0.78 |
| 5 | Senior × GDP growth | 0.2973 | 0.89 | 0.78 |
| 6 | New hires × economic sentiment | 0.3137 | 0.78 | 0.78 |
| … | 9 more tests | 0.46–0.98 | | 0.80–0.98 |

A result counts only if **q < 0.05**. The smallest q is **0.53**, so **nothing counts**: finding 4, "no link found". **Code:** `statsmodels.stats.multitest.multipletests(method="fdr_bh")` in `fit_associations`.

---

## 10. Every headline number, traced

| Number | Where it comes from | How to recompute |
|---|---|---|
| **78.6%** senior | 209 ÷ 266, sum of complete years 2021–2024, `variant = main` | Section 3 table |
| **73.3–83.1%** | Wilson interval on 209 / 266 | Section 6 |
| **81.0%** with Managers | 654 ÷ 807, `variant = sensitivity_manager` | Section 3 |
| **86.8%** new hires | 1,423 ÷ 1,640, 2021–2024 | Section 3 |
| **5.1%** turnover 2025 | 82 ÷ 1,609.7 | Section 4 |
| **0 of 15**, smallest q **0.53** | Benjamini-Hochberg on the 15 within-country p-values | Section 9 |
| **OR 0.82** | Sentiment × regretted turnover, per 5.8-point step | Section 8 |

`scripts/verify_findings.py` recomputes all of these with separate pandas and statsmodels code and prints each pair side by side.

## 11. Limitations to be ready for

| Limitation | What it means |
|---|---|
| Assumptions pending clarification | Senior scope and the headcount rule are config switches; finding 1 holds under both senior definitions |
| No employees hired before 2020 | Turnover trends mix real change with a workforce that is still growing and maturing |
| Small numbers of leavers (57 / 232 / 217) | Only moderate-to-large effects could have been detected; "no evidence of a link" is not "proof of no link" |
| One fixed lag per signal | Checked against real release dates; Ireland publishes unemployment a month earlier (not exploited) |
| Revised values for 4 of 5 signals | Only inflation has first-release values, and inflation turned out never to be revised |
| Time since hire not controlled in the turnover model | Leaving is far more likely early in a job (2.4% a month in the first 6 months vs ~0.5% after 2 years); adding tenure bands is a documented next step |
| Association is not causation | Even a significant result would not show that the economy *caused* people to leave |
