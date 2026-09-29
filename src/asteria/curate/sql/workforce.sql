-- Workforce: source-shaped rows -> canonical employees, with every rule hit recorded.
--
-- Inputs (loaded by curate/pipeline.py):
--   raw_workforce       starter CSV exactly as supplied, all VARCHAR, plus source_row
--   cfg_params          as_of_date
--   cfg_country_alias   accepted code -> canonical ISO alpha-2 (includes EL, ROM)
--   cfg_level_alias     career-level label -> canonical level
--   cfg_allowed         (field, value) accepted categorical values
--   cfg_rules           (rule_id, severity)
-- Outputs: employees, wf_quality_events

-- 1. Exact duplicates: identical on every source column. Keep the first occurrence.
CREATE OR REPLACE TABLE wf_deduped AS
SELECT * EXCLUDE (dup_rank)
FROM (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY employee_id, country_code, business_unit, job_family, career_level,
                employment_type, hire_date, termination_date, termination_type,
                regretted_exit, source_system, record_updated_at
            ORDER BY source_row
        ) AS dup_rank
    FROM raw_workforce
)
WHERE dup_rank = 1;

-- 2. Conflicting versions of one employee_id: keep the latest update.
CREATE OR REPLACE TABLE wf_versions AS
SELECT
    *,
    row_number() OVER (
        PARTITION BY employee_id ORDER BY record_updated_at DESC, source_row DESC
    ) AS version_rank
FROM wf_deduped;

-- 3. Typed and canonical values. Raw values are kept alongside for lineage.
CREATE OR REPLACE TABLE wf_typed AS
SELECT
    v.source_row,
    v.employee_id,
    nullif(trim(v.country_code), '')                     AS country_code_raw,
    ca.canonical                                         AS country_code,
    nullif(trim(v.business_unit), '')                    AS business_unit,
    nullif(trim(v.job_family), '')                       AS job_family,
    nullif(trim(v.career_level), '')                     AS career_level_raw,
    coalesce(la.canonical, nullif(trim(v.career_level), '')) AS career_level,
    nullif(trim(v.employment_type), '')                  AS employment_type,
    nullif(trim(v.hire_date), '')                        AS hire_date_raw,
    try_cast(nullif(trim(v.hire_date), '') AS DATE)      AS hire_date,
    nullif(trim(v.termination_date), '')                 AS termination_date_raw,
    try_cast(nullif(trim(v.termination_date), '') AS DATE) AS termination_date,
    nullif(trim(v.termination_type), '')                 AS termination_type,
    nullif(lower(trim(v.regretted_exit)), '')            AS regretted_exit_raw,
    nullif(trim(v.source_system), '')                    AS source_system,
    try_cast(nullif(trim(v.record_updated_at), '') AS DATE) AS record_updated_at
FROM wf_versions AS v
LEFT JOIN cfg_country_alias AS ca ON ca.code = nullif(trim(v.country_code), '')
LEFT JOIN cfg_level_alias AS la ON la.label = trim(v.career_level)
WHERE v.version_rank = 1;

-- 4. Rule hits, one row per (source row, rule).
CREATE OR REPLACE TABLE wf_quality_events AS
WITH p AS (SELECT as_of_date FROM cfg_params),
allowed AS (SELECT field, value FROM cfg_allowed)
SELECT r.source_row, r.employee_id, 'WF_EXACT_DUPLICATE' AS rule_id
FROM raw_workforce AS r ANTI JOIN wf_deduped AS d USING (source_row)
UNION ALL
SELECT source_row, employee_id, 'WF_ID_SUPERSEDED' FROM wf_versions WHERE version_rank > 1
UNION ALL
SELECT source_row, employee_id, 'WF_COUNTRY_ALIAS' FROM wf_typed
WHERE country_code IS NOT NULL AND country_code <> country_code_raw
UNION ALL
SELECT source_row, employee_id, 'WF_COUNTRY_MISSING' FROM wf_typed WHERE country_code_raw IS NULL
UNION ALL
SELECT source_row, employee_id, 'WF_COUNTRY_UNKNOWN' FROM wf_typed
WHERE country_code_raw IS NOT NULL AND country_code IS NULL
UNION ALL
SELECT source_row, employee_id, 'WF_CAREER_LEVEL_ALIAS' FROM wf_typed
WHERE career_level IS DISTINCT FROM career_level_raw
UNION ALL
SELECT source_row, employee_id, 'WF_CATEGORY_UNKNOWN' FROM wf_typed AS t
WHERE t.business_unit IS NULL
    OR t.business_unit NOT IN (SELECT value FROM allowed WHERE field = 'business_unit')
    OR t.career_level IS NULL
    OR t.career_level NOT IN (SELECT value FROM allowed WHERE field = 'career_level')
    OR t.employment_type IS NULL
    OR t.employment_type NOT IN (SELECT value FROM allowed WHERE field = 'employment_type')
    OR t.source_system NOT IN (SELECT value FROM allowed WHERE field = 'source_system')
    OR t.termination_type NOT IN (SELECT value FROM allowed WHERE field = 'termination_type')
    OR t.regretted_exit_raw NOT IN ('true', 'false')
UNION ALL
SELECT source_row, employee_id, 'WF_DATE_UNPARSEABLE' FROM wf_typed
WHERE (hire_date_raw IS NOT NULL AND hire_date IS NULL)
    OR (termination_date_raw IS NOT NULL AND termination_date IS NULL)
UNION ALL
SELECT source_row, employee_id, 'WF_HIRE_DATE_MISSING' FROM wf_typed WHERE hire_date_raw IS NULL
UNION ALL
SELECT source_row, employee_id, 'WF_HIRE_AFTER_AS_OF' FROM wf_typed, p WHERE hire_date > p.as_of_date
UNION ALL
SELECT source_row, employee_id, 'WF_TERMINATION_BEFORE_HIRE' FROM wf_typed
WHERE termination_date < hire_date
UNION ALL
SELECT source_row, employee_id, 'WF_TERMINATION_AFTER_AS_OF' FROM wf_typed, p
WHERE termination_date > p.as_of_date
UNION ALL
SELECT source_row, employee_id, 'WF_TERMINATION_TYPE_MISSING' FROM wf_typed
WHERE termination_date_raw IS NOT NULL AND termination_type IS NULL
UNION ALL
SELECT source_row, employee_id, 'WF_TYPE_WITHOUT_DATE' FROM wf_typed
WHERE termination_date_raw IS NULL AND termination_type IS NOT NULL
UNION ALL
SELECT source_row, employee_id, 'WF_REGRETTED_UNKNOWN' FROM wf_typed
WHERE termination_type = 'Voluntary' AND regretted_exit_raw IS NULL
UNION ALL
SELECT source_row, employee_id, 'WF_REGRETTED_NOT_VOLUNTARY' FROM wf_typed
WHERE termination_type IS DISTINCT FROM 'Voluntary' AND regretted_exit_raw = 'true'
UNION ALL
SELECT source_row, employee_id, 'WF_EOC_ON_PERMANENT' FROM wf_typed
WHERE termination_type = 'End of Contract' AND employment_type = 'Permanent';

-- 5. Canonical employees: one row per employee_id, measurability decided by rule severity.
CREATE OR REPLACE TABLE employees AS
WITH p AS (SELECT as_of_date FROM cfg_params),
hits AS (
    SELECT
        e.source_row,
        list(DISTINCT e.rule_id ORDER BY e.rule_id)                        AS quality_rules,
        bool_or(r.severity = 'exclude')                                    AS has_exclude,
        bool_or(r.severity = 'exclude_country')                            AS has_exclude_country
    FROM wf_quality_events AS e JOIN cfg_rules AS r USING (rule_id)
    GROUP BY e.source_row
),
typed AS (
    SELECT
        t.*,
        -- A termination after the as-of date is not yet known: the employee is active.
        CASE WHEN t.termination_date <= p.as_of_date THEN t.termination_date END AS exit_date
    FROM wf_typed AS t, p
)
SELECT
    t.employee_id,
    t.country_code,
    t.business_unit,
    t.job_family,
    t.career_level,
    t.employment_type,
    t.hire_date,
    t.exit_date,
    CASE WHEN t.exit_date IS NOT NULL THEN t.termination_type END          AS exit_type,
    CASE
        WHEN t.exit_date IS NULL THEN 'not_applicable'
        WHEN t.termination_type <> 'Voluntary' OR t.termination_type IS NULL THEN 'not_applicable'
        WHEN t.regretted_exit_raw = 'true' THEN 'regretted'
        WHEN t.regretted_exit_raw = 'false' THEN 'not_regretted'
        ELSE 'unknown'
    END                                                                    AS regretted_status,
    NOT coalesce(h.has_exclude, false)                                     AS is_measurable,
    NOT coalesce(h.has_exclude, false) AND NOT coalesce(h.has_exclude_country, false)
                                                                           AS in_country_scope,
    coalesce(h.quality_rules, [])                                          AS quality_rules,
    -- Lineage
    t.country_code_raw,
    t.career_level_raw,
    t.hire_date_raw,
    t.termination_date_raw,
    t.regretted_exit_raw,
    t.source_system,
    t.record_updated_at,
    t.source_row
FROM typed AS t
LEFT JOIN hits AS h USING (source_row)
ORDER BY t.employee_id;
