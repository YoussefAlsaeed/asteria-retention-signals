-- Retention objectives: auditable numerators and denominators for every slice and period.
--
-- Inputs (prepared by analytics/pipeline.py):
--   emp                   canonical employees + segment_value (the configured segment)
--   cfg_analysis          as_of_date, reporting_start, min_sample
--   cfg_objectives        objective_id, measure, months, direction, target, effective_to
--   cfg_objective_levels  (objective_id, variant, level): eligible career levels per variant
-- Outputs: mart_cohort_members, mart_person_months, mart_objective_measures
--
-- Slices: country_code 'ALL' = company-wide (includes employees with an unknown country);
-- a country slice uses only employees in country scope. segment_value 'All' = every segment.

-- Wilson 95% interval. Undefined (NULL) unless 0 <= k <= n: a turnover numerator can
-- exceed a tiny slice's *average* headcount, and the binomial interval then has no meaning.
CREATE OR REPLACE MACRO wilson_low(k, n) AS CASE WHEN n > 0 AND k >= 0 AND k <= n THEN
    (k / n + 1.96 * 1.96 / (2 * n)
     - 1.96 * sqrt((k / n) * (1 - k / n) / n + 1.96 * 1.96 / (4 * n * n)))
    / (1 + 1.96 * 1.96 / n) END;
CREATE OR REPLACE MACRO wilson_high(k, n) AS CASE WHEN n > 0 AND k >= 0 AND k <= n THEN
    (k / n + 1.96 * 1.96 / (2 * n)
     + 1.96 * sqrt((k / n) * (1 - k / n) / n + 1.96 * 1.96 / (4 * n * n)))
    / (1 + 1.96 * 1.96 / n) END;

CREATE OR REPLACE VIEW emp_scoped AS
SELECT *, CASE WHEN in_country_scope THEN country_code ELSE '(unassigned)' END AS country_key
FROM emp
WHERE is_measurable;

-- 1. Cohort members: one row per eligible hire per objective variant.
--    Lost = exited before the N-month anniversary (calendar months; employed through the
--    anniversary counts as retained). A cohort month is mature only when every member's
--    anniversary is on or before the as-of date.
CREATE OR REPLACE TABLE mart_cohort_members AS
SELECT
    o.objective_id,
    l.variant,
    e.employee_id,
    e.country_key,
    e.segment_value,
    date_trunc('month', e.hire_date)::DATE                                  AS cohort_month,
    e.hire_date,
    e.exit_date,
    (e.hire_date + to_months(o.months))::DATE                               AS anniversary,
    coalesce(e.exit_date < (e.hire_date + to_months(o.months))::DATE, false) AS lost,
    (last_day(e.hire_date) + to_months(o.months))::DATE <= p.as_of_date     AS cohort_mature
FROM cfg_objectives AS o
JOIN cfg_objective_levels AS l USING (objective_id)
JOIN emp_scoped AS e ON e.career_level = l.level
CROSS JOIN cfg_analysis AS p
WHERE o.measure = 'cohort_retention'
  AND e.hire_date >= p.reporting_start
  AND e.hire_date <= o.effective_to;

-- 2. Cohort measures per hire month, for every country x segment slice.
CREATE OR REPLACE TABLE cohort_monthly AS
SELECT
    objective_id,
    variant,
    cohort_month,
    CASE WHEN grouping(country_key) = 1 THEN 'ALL' ELSE country_key END   AS country_code,
    CASE WHEN grouping(segment_value) = 1 THEN 'All' ELSE segment_value END AS segment_value,
    count(*)                                                               AS denominator,
    count(*) FILTER (WHERE NOT lost)                                       AS numerator,
    bool_and(cohort_mature)                                                AS is_mature
FROM mart_cohort_members
GROUP BY GROUPING SETS (
    (objective_id, variant, cohort_month, country_key, segment_value),
    (objective_id, variant, cohort_month, country_key),
    (objective_id, variant, cohort_month, segment_value),
    (objective_id, variant, cohort_month)
)
HAVING country_code <> '(unassigned)';

-- Roll hire months up to quarters and years. Maturity is a property of the period (its
-- last possible hire must have reached the anniversary), not of the hires that happen to
-- exist in a slice: a small slice with no late hires must not look mature early.
CREATE OR REPLACE TABLE cohort_measures AS
WITH rolled AS (
    SELECT objective_id, variant, 'month' AS grain, cohort_month AS period_start,
           last_day(cohort_month) AS period_end, country_code, segment_value,
           numerator, denominator
    FROM cohort_monthly
    UNION ALL
    SELECT objective_id, variant, grain, period_start,
           last_day(period_start + to_months(CASE grain WHEN 'quarter' THEN 2 ELSE 11 END)),
           country_code, segment_value, sum(numerator), sum(denominator)
    FROM (
        SELECT c.*, g.grain, date_trunc(g.grain, c.cohort_month)::DATE AS period_start
        FROM cohort_monthly AS c, (VALUES ('quarter'), ('year')) AS g(grain)
    )
    GROUP BY objective_id, variant, grain, period_start, country_code, segment_value
)
SELECT r.objective_id, r.variant, r.grain, r.period_start, r.period_end, r.country_code,
       r.segment_value, r.numerator, r.denominator::DOUBLE AS denominator,
       (r.period_end + to_months(o.months))::DATE <= p.as_of_date AS is_mature
FROM rolled AS r
JOIN cfg_objectives AS o USING (objective_id)
CROSS JOIN cfg_analysis AS p;

-- 3. Person-months at risk of a regretted exit (also the unit for the hazard model).
--    At risk in month m: hired before m starts and not exited before m starts.
CREATE OR REPLACE TABLE mart_person_months AS
WITH months AS (
    SELECT range::DATE AS month_start
    FROM range(
        (SELECT min(date_trunc('month', hire_date)) FROM emp_scoped),
        (SELECT as_of_date FROM cfg_analysis) + INTERVAL 1 DAY,
        INTERVAL 1 MONTH
    )
)
SELECT
    e.employee_id,
    e.country_key,
    e.segment_value,
    m.month_start,
    coalesce(e.exit_date <= last_day(m.month_start), false)                AS exits_in_month,
    coalesce(e.exit_date <= last_day(m.month_start), false)
        AND e.regretted_status = 'regretted'                               AS regretted_exit,
    coalesce(e.exit_date <= last_day(m.month_start), false)
        AND e.regretted_status IN ('regretted', 'unknown')                 AS regretted_exit_upper
FROM emp_scoped AS e
JOIN months AS m
    ON e.hire_date < m.month_start
   AND (e.exit_date IS NULL OR e.exit_date >= m.month_start);

-- 4. Trailing twelve-month regretted turnover.
--    Numerator: regretted exits with exit date in the 12 months ending at month end M.
--    Denominator: mean of the 12 month-end headcounts in that window.
CREATE OR REPLACE TABLE turnover_monthly AS
WITH month_ends AS (
    SELECT last_day(range)::DATE AS month_end
    FROM range(
        (SELECT min(date_trunc('month', hire_date)) FROM emp_scoped),
        (SELECT as_of_date FROM cfg_analysis) + INTERVAL 1 DAY,
        INTERVAL 1 MONTH
    )
),
headcount AS (
    SELECT m.month_end, e.country_key, e.segment_value, count(*) AS headcount
    FROM month_ends AS m
    JOIN emp_scoped AS e
        ON e.hire_date <= m.month_end AND (e.exit_date IS NULL OR e.exit_date > m.month_end)
    GROUP BY ALL
),
exits AS (
    SELECT last_day(exit_date)::DATE AS month_end, country_key, segment_value,
           count(*) FILTER (WHERE regretted_status = 'regretted')               AS regretted,
           count(*) FILTER (WHERE regretted_status IN ('regretted', 'unknown')) AS regretted_upper
    FROM emp_scoped
    WHERE exit_date IS NOT NULL
    GROUP BY ALL
),
base AS (
    SELECT m.month_end, k.country_key, k.segment_value,
           coalesce(h.headcount, 0) AS headcount,
           coalesce(x.regretted, 0) AS regretted,
           coalesce(x.regretted_upper, 0) AS regretted_upper
    FROM month_ends AS m
    CROSS JOIN (SELECT DISTINCT country_key, segment_value FROM emp_scoped) AS k
    LEFT JOIN headcount AS h USING (month_end, country_key, segment_value)
    LEFT JOIN exits AS x USING (month_end, country_key, segment_value)
),
sliced AS (
    SELECT
        month_end,
        CASE WHEN grouping(country_key) = 1 THEN 'ALL' ELSE country_key END     AS country_code,
        CASE WHEN grouping(segment_value) = 1 THEN 'All' ELSE segment_value END AS segment_value,
        sum(headcount) AS headcount, sum(regretted) AS regretted,
        sum(regretted_upper) AS regretted_upper
    FROM base
    GROUP BY GROUPING SETS (
        (month_end, country_key, segment_value), (month_end, country_key),
        (month_end, segment_value), (month_end)
    )
    HAVING country_code <> '(unassigned)'
)
SELECT
    month_end,
    country_code,
    segment_value,
    sum(regretted) OVER w       AS regretted_ttm,
    sum(regretted_upper) OVER w AS regretted_upper_ttm,
    avg(headcount) OVER w       AS avg_headcount_ttm,
    count(*) OVER w             AS months_in_window
FROM sliced
WINDOW w AS (
    PARTITION BY country_code, segment_value ORDER BY month_end
    ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
);

-- Month grain = TTM ending that month; quarter/year grain = TTM at the period's last month.
CREATE OR REPLACE TABLE turnover_measures AS
SELECT
    'REGRETTED_TURNOVER_12M' AS objective_id,
    v.variant,
    g.grain,
    date_trunc(g.grain, t.month_end)::DATE                    AS period_start,
    t.month_end                                               AS period_end,
    t.country_code,
    t.segment_value,
    CASE v.variant WHEN 'main' THEN t.regretted_ttm ELSE t.regretted_upper_ttm END AS numerator,
    t.avg_headcount_ttm                                       AS denominator,
    true                                                      AS is_mature
FROM turnover_monthly AS t
CROSS JOIN (VALUES ('main'), ('upper_bound_unknown')) AS v(variant)
CROSS JOIN (VALUES ('month'), ('quarter'), ('year')) AS g(grain)
CROSS JOIN cfg_analysis AS p
WHERE t.months_in_window = 12
  AND t.month_end >= p.reporting_start
  AND (g.grain = 'month'
       OR (g.grain = 'quarter' AND month(t.month_end) IN (3, 6, 9, 12))
       OR (g.grain = 'year' AND month(t.month_end) = 12));

-- 5. One consumption table for every objective, with uncertainty and status.
CREATE OR REPLACE TABLE mart_objective_measures AS
WITH unioned AS (
    SELECT * FROM cohort_measures
    UNION ALL
    SELECT * FROM turnover_measures
)
SELECT
    u.objective_id,
    u.variant,
    u.grain,
    u.period_start,
    u.period_end,
    u.country_code,
    u.segment_value,
    u.numerator,
    u.denominator,
    CASE WHEN u.is_mature AND u.denominator > 0 THEN u.numerator / u.denominator END AS rate,
    CASE WHEN u.is_mature THEN wilson_low(u.numerator::DOUBLE, u.denominator) END  AS ci_low,
    CASE WHEN u.is_mature THEN wilson_high(u.numerator::DOUBLE, u.denominator) END AS ci_high,
    o.target,
    o.direction,
    CASE
        WHEN NOT u.is_mature THEN 'pending'
        WHEN u.denominator < p.min_sample THEN 'insufficient_sample'
        WHEN (o.direction = 'at_least' AND u.numerator / u.denominator >= o.target)
          OR (o.direction = 'at_most' AND u.numerator / u.denominator <= o.target) THEN 'met'
        ELSE 'not_met'
    END AS status,
    -- "clear" when the 95% interval lies entirely on one side of the target
    CASE
        WHEN NOT u.is_mature OR u.denominator < p.min_sample THEN NULL
        WHEN wilson_low(u.numerator::DOUBLE, u.denominator) > o.target
          OR wilson_high(u.numerator::DOUBLE, u.denominator) < o.target THEN 'clear'
        ELSE 'within_uncertainty'
    END AS confidence
FROM unioned AS u
JOIN cfg_objectives AS o USING (objective_id)
CROSS JOIN cfg_analysis AS p
ORDER BY u.objective_id, u.variant, u.grain, u.country_code, u.segment_value, u.period_start;
