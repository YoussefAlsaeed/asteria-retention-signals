-- Point-in-time external signals: what was knowable at the start of each month.
--
-- Inputs: external_observations (curated), cfg_signals (indicator, release, lag_days),
--         cfg_analysis (as_of_date)
-- Output: mart_signal_asof, one row per (as_of month, country, indicator)
--
-- No future information: a value is usable only from available_from = period_end + lag.
-- Frequency integrity: a carried-forward value keeps its own period, frequency, status and
-- age. In March 2023 the latest usable annual GDP figure is 2021 (2022 is not yet
-- published), reported as "2021, ~14 months old", never as a March 2023 measurement.

CREATE OR REPLACE TABLE mart_signal_values AS
SELECT
    o.indicator_id,
    o.country_code,
    o.frequency,
    o.period_start,
    o.period_end,
    o.value,
    o.status,
    o.status_label,
    (o.period_end + to_days(s.lag_days))::DATE AS available_from
FROM external_observations AS o
JOIN cfg_signals AS s
    ON s.indicator_id = o.indicator_id
   AND s.release_code IS NOT DISTINCT FROM o.release_code;

CREATE OR REPLACE TABLE mart_signal_asof AS
WITH grid AS (
    SELECT m.range::DATE AS as_of_date, c.country_code, s.indicator_id
    FROM range(DATE '2020-01-01', (SELECT as_of_date FROM cfg_analysis) + INTERVAL 1 DAY,
               INTERVAL 1 MONTH) AS m
    CROSS JOIN (SELECT DISTINCT country_code FROM external_observations) AS c
    CROSS JOIN cfg_signals AS s
)
SELECT
    g.as_of_date,
    g.country_code,
    g.indicator_id,
    v.value,
    v.frequency                                   AS signal_frequency,
    v.period_start                                AS signal_period_start,
    v.period_end                                  AS signal_period_end,
    v.available_from,
    date_diff('day', v.period_end, g.as_of_date)  AS signal_age_days,
    v.status                                      AS signal_status,
    v.status_label                                AS signal_status_label
FROM grid AS g
ASOF LEFT JOIN mart_signal_values AS v
    ON v.indicator_id = g.indicator_id
   AND v.country_code = g.country_code
   AND g.as_of_date >= v.available_from
ORDER BY g.indicator_id, g.country_code, g.as_of_date;
