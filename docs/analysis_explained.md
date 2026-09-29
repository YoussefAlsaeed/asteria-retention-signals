# How the findings were produced: a developer's guide

For engineers who want to understand and check the analysis without a statistics background. Every number here can be reproduced:

```sh
uv run asteria run                        # rebuild everything from the committed inputs (offline)
uv run python scripts/verify_findings.py  # recompute every finding with separate pandas code
```

`verify_findings.py` does not import the pipeline. It reads the curated CSVs and redoes the maths independently, then compares 107 numbers with the pipeline's output. Last run: **107 / 107 agree**.

---

## 1. The whole thing in one picture

```
 Starter CSV (2,407 rows)            Eurostat + World Bank APIs (6 series)
          │                                        │
          ▼                                        ▼
   CURATE: clean, dedupe, flag            INGEST: download, checksum, store
          │                                        │
          ▼                                        ▼
   employees (2,400 people)          external_observations (2,456 values)
          │                                        │
          ├──► Findings 1-3: count who stayed      │
          │    (employee data only)                 │
          │                                        ▼
          └──────────────► Finding 4: join each person to "the economy as it
                           was known at the time", then test for a pattern
```

Your reading is right: **findings 1–3 use only the cleaned employee data. Finding 4 is the only one that uses the external data.**

---

## 2. The data we have

### 2a. The employee file

One row per person. The fields that matter:

| Field | Meaning | Example |
|---|---|---|
| `hire_date` | First day of work | 2022-01-08 |
| `exit_date` | Last day (blank = still employed on 2025-12-31) | 2022-04-27 |
| `exit_type` | Voluntary (quit), Involuntary (let go), End of Contract | Voluntary |
| `regretted_status` | `regretted` = a quit the company did not want | regretted |
| `career_level` | Individual Contributor / Manager / Senior Leader | Senior Leader |
| `country_code`, `business_unit` | Where the person works | GR, Sales |

**What cleaning did** (full list: [data/curated/quality_report.md](../data/curated/quality_report.md)):

- Removed 7 exact duplicate rows, so 2,407 rows became 2,400 people.
- Fixed codes: 8 non-standard country codes (`EL` → GR, `ROM` → RO) and 10 `Sr Mgmt` labels → Senior Leader (an assumption).
- Excluded 10 people from every calculation: 5 with no hire date and 5 who "left before they joined". Measurable people: **2,390**.
- 9 people have no country. They count in company-wide numbers but not in any country's, so the country figures cover 2,381.
- Nothing is deleted silently. Each person has `is_measurable`, `in_country_scope` and a `quality_rules` list in [employees.csv](../data/curated/employees.csv).

### 2b. The external data

Six monthly, quarterly or annual numbers per country, downloaded from official statistics offices:

| Series | What it measures, in plain words | Greece, June 2023 | Ireland, June 2023 | How often |
|---|---|---:|---:|---|
| `unemployment_rate` | % of people who want a job but have none | 11.7 | 4.3 | monthly |
| `job_vacancy_rate` | % of jobs that are open and unfilled | 1.6 (Q2) | 1.3 (Q2) | quarterly |
| `hicp_inflation_first_release` | How much prices rose vs a year earlier, as first announced | 2.8 | 4.9 | monthly |
| `economic_sentiment` | Survey of how confident businesses and consumers feel (100 = normal) | 109.0 | 100.9 | monthly |
| `gdp_growth` | How much the economy grew that year | 2.1 (2023) | −2.5 (2023) | yearly |

These come as raw JSON in [data/raw-or-fixtures/sources/](../data/raw-or-fixtures/sources/), are cleaned into [external_observations.csv](../data/curated/external_observations.csv), and are documented with licences and limitations in [source_register.md](source_register.md).

---

## 3. Findings 1–3: counting who stayed

These are plain counting. No statistics goes into the numbers themselves; statistics is only used for the error bars.

### The three metrics as code

```python
# NEW_HIRE_6M and SENIOR_HIRE_12M: "of the people hired, how many were still here N months later?"
anniversary = hire_date + months(N)          # calendar months: 31 Jan + 6 = 31 Jul
lost        = exit_date is not None and exit_date < anniversary
retention   = count(not lost) / count(hired)  # per hire month, then rolled up to quarter/year

# REGRETTED_TURNOVER_12M: "of our average workforce, what share left and we regret it?"
regretted_exits = count(exits in the last 12 months where regretted_status == "regretted")
avg_headcount   = mean(headcount on each of the last 12 month-ends)
turnover        = regretted_exits / avg_headcount
```

The real implementation is SQL in [src/asteria/analytics/sql/retention.sql](../src/asteria/analytics/sql/retention.sql). The definitions (6 or 12 months, who counts as senior) are in [config/analysis.yaml](../config/analysis.yaml).

### Worked example

Employee `ACP000359`: Senior Leader, hired 2022-01-08, quit 2022-04-27, regretted.

- **SENIOR_HIRE_12M:** anniversary 2023-01-08; quit before it, so **lost**. They count against the 2022 senior cohort.
- **NEW_HIRE_6M:** anniversary 2022-07-08; quit before it, so also **lost**.
- **REGRETTED_TURNOVER_12M:** one regretted exit in April 2022. It is in the numerator of every 12-month window that includes April 2022.

### Two rules that stop us cheating

1. **Unfinished cohorts are "pending", not "retained".** Someone hired in October 2025 hasn't had 6 months yet, since the data stops at 2025-12-31. Counting them as "stayed" would inflate retention, so any hire month whose window hasn't finished is marked `pending` with no rate. That's why 2025 is pending for both hire-based objectives.
2. **Pooling adds counts, not percentages.** "2021–2024 pooled" means (sum retained) / (sum hired) across the four years, so big and small years are weighted correctly.

### Error bars: why "met" is not always "met"

Hiring 10 people and keeping 9 gives 90%. With 10 people, though, one departure moves the number by 10 points, so the true rate could plausibly be anywhere from about 60% to 98%. Every rate comes with a **95% interval** (Wilson method): the range the true rate probably lies in. Small groups get wide ranges, large groups get narrow ones.

Each result then gets a `confidence` label:
- `clear`: the whole range is on one side of the target, so we're confident about met or not met.
- `within_uncertainty`: the range crosses the target, so it's too close to call.

| Finding | Numbers | What it means |
|---|---|---|
| **1. Senior hires** | 209 of 266 kept = **78.6%**, range 73.3–83.1%, target ≥ 90% | Missed, and **clearly**: even the top of the range is below 90%. Counting Managers as senior gives 81.0%, still clearly missed, so the answer doesn't depend on that assumption. |
| **2. New hires** | 1,423 of 1,640 kept = **86.8%**, range 85.0–88.3%, target ≥ 86% | "Met", but the range includes 86%, so it's on the line. Countries range from 84.7% to 89.2% and all overlap the target, so no country is a proven outlier. |
| **3. Regretted turnover** | 4.3% → 3.7% → 3.3% → 3.3% → **5.1%** (2021–2025), limit ≤ 7.5% | Clearly within the limit every year, but 2025 rose (82 regretted exits vs 46). |

**A caveat for finding 3:** nobody in the file was hired before 2020, so the company "starts" with zero staff in January 2020 and grows to about 1,600. Early years therefore have small, very new workforces. Some of the 2025 rise may simply be that more people have now been around long enough to quit. We report the rise but don't claim a cause.

**Where to see every number:** [objective_measures.csv](../data/curated/objective_measures.csv) has one row per objective × country × business unit × period, with `numerator`, `denominator`, `rate`, `ci_low`, `ci_high`, `status` and `confidence`. Filter `variant=main`, `grain=year`, `country_code=ALL`, `segment_value=All` for the headline figures.

---

## 4. Finding 4: did the economy make a difference?

The question: when unemployment was higher (or inflation, or confidence), did people leave more or less? It takes three steps.

### Step 1: join each person to the economy *as it was known at the time*

The trap is using numbers that hadn't been published yet. March's unemployment figure only comes out around late May, so it can't explain a decision someone made in April.

Think of it like `git checkout` at a date: for each month we use only the values already published by the first day of that month. Each series has a publication delay (`lag_days` in [config/analysis.yaml](../config/analysis.yaml)), set conservatively and spot-checked against official release dates ([source register](source_register.md)).

**What someone in Greece knew on 1 June 2023** (from [signal_asof.csv](../data/curated/signal_asof.csv)):

| Series | Value used | Which period it describes | How old |
|---|---:|---|---:|
| economic_sentiment | 108.0 | April 2023 | 32 days (May's figure came out on 30 May, but the rule waits 10 days) |
| inflation (first release) | 4.5 | April 2023 | 32 days |
| unemployment_rate | 11.4 | March 2023 | 62 days |
| job_vacancy_rate | 0.9 | Q4 2022 | 152 days |
| gdp_growth | 8.7 | **year 2021** | 517 days |

Note GDP: in June 2023 the 2022 annual figure wasn't out yet, so the 2021 figure is used, and **labelled as 2021, 517 days old**. It is never presented as a June 2023 measurement. That's the brief's "frequency integrity" rule.

The SQL is a DuckDB `ASOF JOIN` in [signals.sql](../src/asteria/analytics/sql/signals.sql). A test checks that no value is ever used before its publication date.

Each hire is matched to the economy **in their hire month**. For turnover, each person is matched to the economy **in each month they were employed**, giving 65,184 person-months.

### Step 2: fit a model that looks for a pattern

The model is a **logistic regression**. For a developer: it's a function fitted to the data that predicts *probability of leaving* from some inputs, and it tells you how much each input moves that probability.

The number we report is the **odds ratio** (OR):
- **OR = 1.0:** the signal makes no difference.
- **OR = 1.2:** a step up in the signal goes with 20% higher odds of leaving.
- **OR = 0.8:** a step up goes with 20% lower odds of leaving.
- The OR also has a 95% range. **If the range includes 1.0, we can't tell it apart from "no effect".**

A "step" is one typical swing of that signal within a country (one within-country standard deviation), so all five signals are on a comparable scale.

### Step 3: remove the two biggest sources of false patterns

**Country differences.** Greece has high unemployment and Ireland low unemployment, but they also differ in labour law, culture and pay. A naive model would credit unemployment for whatever makes Greece different from Ireland. The fix is to give each country its own baseline (called **country fixed effects**), so Greece is only ever compared with Greece in a different month.

**Time drift.** If the economy and quitting both drift over 2021–2025 for unrelated reasons, they'll look linked. The fix is a **time trend** term that absorbs the common drift.

**Honest sample size.** Everyone in Greece in the same month shares the same unemployment value. Forty people in one month are not forty independent pieces of evidence about unemployment, much as one flaky test run forty times doesn't count as forty passes. The errors are **clustered** on country + month to account for this.

We fit both versions, so you can see what the corrections change. For unemployment and regretted exits, the naive OR is 0.97 and the country-corrected OR is 1.11: **the direction flips**, which shows exactly why the correction is needed.

### Step 4: correct for running many tests

We ran 30 models: 3 objectives × 5 signals × (naive and corrected). The **p-value** is how likely a pattern this strong would be by pure luck. At the usual threshold (p < 0.05), about 1 in 20 tests "passes" by luck, so 30 tests would produce about 1.5 false alarms even with no real effects.

The **q-value** (Benjamini-Hochberg correction) adjusts for that, like requiring a flaky test to pass consistently before trusting it. A result counts only if q is small (typically < 0.05).

### Result

| Objective | Strongest signal | OR (corrected) | 95% range | q |
|---|---|---:|---|---:|
| Regretted turnover | economic sentiment | 0.82 | 0.68–0.99 | 0.53 |
| Regretted turnover | GDP growth | 0.89 | 0.77–1.02 | 0.65 |
| Senior hires | GDP growth | 0.84 | 0.61–1.16 | 0.78 |
| New hires | economic sentiment | 1.07 | 0.94–1.21 | 0.78 |

The full table is in [association_results.csv](../data/curated/association_results.csv) and [analysis_summary.md](../data/curated/analysis_summary.md).

**No q-value is below 0.53, so no signal is linked to any objective.** The one interesting hint (higher business confidence going with fewer regretted exits, p = 0.04) is about what luck alone would produce across 30 tests, so we don't claim it.

### Why a non-finding is a real result

- The brief explicitly asks for at least one limitation or non-finding.
- We checked we *could* have found an effect: on synthetic data with a planted effect, the same code finds it, and on synthetic data with only country differences, the naive model is fooled while the corrected one is not ([tests/analytics/test_association.py](../tests/analytics/test_association.py)).
- **The sample is small for this question:** 57 senior early exits, 232 new-hire early exits and 217 regretted exits across six countries and five years. Only fairly large effects could have been detected. "No evidence of an effect" is **not** "evidence of no effect".
- Even a strong pattern would be association, not causation.

---

## 5. Limitations to be able to explain

| Limitation | Effect |
|---|---|
| Metric definitions use our assumptions (clarification answers pending) | Senior scope and the headcount rule are switchable in `config/analysis.yaml`. Finding 1 holds under both senior definitions. |
| No pre-2020 employees | Turnover trends mix real change with a growing, ageing workforce |
| Only inflation has "as first published" values | Other series use today's revised figures, a small look-ahead risk |
| Publication lags are one fixed delay per series | Spot-checked against official release dates for 2021–2026 (source register): every value is used only after its real release. |
| Italy's vacancy rate uses a different definition (Eurostat flag) | The within-country model is unaffected; cross-country vacancy comparisons are not |
| Six countries, about five years | Low statistical power for economy-level effects |

---

## 6. Poke at it yourself

```sh
# PowerShell: $env:PYTHONIOENCODING="utf-8"   bash: export PYTHONIOENCODING=utf-8
uv run python -c "import duckdb; c = duckdb.connect('data/curated/asteria.duckdb', read_only=True); print(c.sql(\"SELECT * FROM mart_objective_measures WHERE grain = 'year' AND country_code = 'ALL' AND segment_value = 'All' AND variant = 'main'\"))"
```

Useful tables in `data/curated/asteria.duckdb`:

| Table | One row per |
|---|---|
| `employees` | person, after cleaning |
| `mart_cohort_members` | person × objective (hire cohorts), with `lost` |
| `mart_person_months` | person × month employed (turnover model) |
| `mart_objective_measures` | objective × country × business unit × period |
| `mart_signal_asof` | country × month × signal: the value known then |
| `mart_association_results` | objective × signal × model |
