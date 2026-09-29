-- External indicators: source-shaped observations -> canonical country-period values.
--
-- Inputs (loaded by curate/pipeline.py):
--   stg_external    one row per provider observation (provider codes and period strings)
--   cfg_geo_map     (provider, geo) -> canonical ISO alpha-2 country
--   cfg_indicators  indicator_id -> lens, title, unit, frequency
-- Outputs: external_observations, external_coverage, ex_quality_events
--
-- Frequency integrity: every value keeps its own frequency and its full period
-- [period_start, period_end]. Nothing is spread to a finer grain here.

-- 1. Canonical country and real date bounds for each provider period.
CREATE OR REPLACE TABLE ext_typed AS
WITH parsed AS (
    SELECT
        s.*,
        g.country_code,
        CASE s.frequency
            WHEN 'M' THEN try_strptime(s.source_period || '-01', '%Y-%m-%d')::DATE
            WHEN 'Q' THEN CASE WHEN regexp_matches(s.source_period, '^\d{4}-Q[1-4]$') THEN
                make_date(CAST(left(s.source_period, 4) AS INTEGER),
                          (CAST(right(s.source_period, 1) AS INTEGER) - 1) * 3 + 1, 1) END
            WHEN 'A' THEN CASE WHEN regexp_matches(s.source_period, '^\d{4}$') THEN
                make_date(CAST(s.source_period AS INTEGER), 1, 1) END
        END AS period_start,
        CASE s.frequency WHEN 'M' THEN 1 WHEN 'Q' THEN 3 WHEN 'A' THEN 12 END AS period_months
    FROM stg_external AS s
    LEFT JOIN cfg_geo_map AS g ON g.provider = s.provider AND g.geo = s.geo
)
SELECT
    *,
    last_day(period_start + to_months(period_months - 1)) AS period_end
FROM parsed;

-- 2. Rule hits. The grain is (indicator, country, period, release).
CREATE OR REPLACE TABLE ex_quality_events AS
SELECT indicator_id, geo, source_period, release_code, 'EX_GEO_UNMAPPED' AS rule_id
FROM ext_typed WHERE country_code IS NULL
UNION ALL
SELECT indicator_id, geo, source_period, release_code, 'EX_PERIOD_UNPARSEABLE'
FROM ext_typed WHERE period_start IS NULL
UNION ALL
SELECT indicator_id, geo, source_period, release_code, 'EX_GRAIN_DUPLICATE'
FROM ext_typed
GROUP BY ALL HAVING count(*) > 1
UNION ALL
SELECT indicator_id, geo, source_period, release_code, 'EX_VALUE_MISSING'
FROM ext_typed WHERE value IS NULL
UNION ALL
SELECT indicator_id, geo, source_period, release_code, 'EX_STATUS_FLAGGED'
FROM ext_typed WHERE value IS NOT NULL AND status IS NOT NULL
UNION ALL
-- Gaps: expected periods between a series' first and last value that have no value.
SELECT e.indicator_id, e.geo, strftime(e.expected_start, '%Y-%m-%d'), e.release_code,
       'EX_PERIOD_GAP'
FROM (
    SELECT
        indicator_id, geo, release_code,
        unnest(generate_series(min(period_start), max(period_start),
                               to_months(any_value(period_months)))) AS expected_start
    FROM ext_typed
    WHERE value IS NOT NULL AND period_start IS NOT NULL
    GROUP BY indicator_id, geo, release_code
) AS e
ANTI JOIN ext_typed AS t
    ON t.indicator_id = e.indicator_id AND t.geo = e.geo
    AND t.release_code IS NOT DISTINCT FROM e.release_code
    AND t.period_start = e.expected_start AND t.value IS NOT NULL;

-- 3. Canonical values. Only rows with a value, a mapped country and a parsed period.
CREATE OR REPLACE TABLE external_observations AS
WITH flags AS (
    SELECT indicator_id, geo, source_period, release_code,
           list(DISTINCT rule_id ORDER BY rule_id) AS quality_rules
    FROM ex_quality_events
    GROUP BY ALL
)
SELECT
    t.indicator_id,
    i.lens,
    t.country_code,
    t.frequency,
    t.period_start,
    t.period_end,
    t.value,
    i.unit,
    t.status,
    t.status_label,
    t.release_code,
    coalesce(f.quality_rules, [])     AS quality_rules,
    -- Lineage
    t.provider,
    t.dataset,
    t.geo                             AS source_geo,
    t.source_period,
    t.source_updated,
    t.fetched_at                      AS loaded_at,
    t.snapshot_sha256
FROM ext_typed AS t
JOIN cfg_indicators AS i USING (indicator_id)
LEFT JOIN flags AS f
    ON f.indicator_id = t.indicator_id AND f.geo = t.geo AND f.source_period = t.source_period
    AND f.release_code IS NOT DISTINCT FROM t.release_code
WHERE t.value IS NOT NULL AND t.country_code IS NOT NULL AND t.period_start IS NOT NULL
ORDER BY t.indicator_id, t.country_code, t.release_code NULLS FIRST, t.period_start;

-- 4. Coverage and freshness per series, for the dashboard's trust view.
CREATE OR REPLACE TABLE external_coverage AS
WITH series_geo AS (
    SELECT DISTINCT indicator_id, geo, country_code FROM ext_typed
),
gaps AS (
    SELECT s.indicator_id, s.country_code, q.release_code, count(*) AS gaps
    FROM ex_quality_events AS q JOIN series_geo AS s USING (indicator_id, geo)
    WHERE q.rule_id = 'EX_PERIOD_GAP'
    GROUP BY ALL
)
SELECT
    o.indicator_id,
    o.lens,
    o.country_code,
    o.release_code,
    o.frequency,
    min(o.period_start)          AS first_period_start,
    max(o.period_end)            AS last_period_end,
    count(*)                     AS values_present,
    coalesce(any_value(g.gaps), 0) AS gaps,
    max(o.source_updated)        AS source_updated,
    max(o.loaded_at)             AS loaded_at
FROM external_observations AS o
LEFT JOIN gaps AS g
    ON g.indicator_id = o.indicator_id AND g.country_code = o.country_code
    AND g.release_code IS NOT DISTINCT FROM o.release_code
GROUP BY o.indicator_id, o.lens, o.country_code, o.release_code, o.frequency
ORDER BY o.indicator_id, o.country_code, o.release_code NULLS FIRST;
