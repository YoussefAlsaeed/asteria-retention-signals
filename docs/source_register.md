# Source register

Every external source, with the evidence behind it. Access date for all checks: **2026-09-28**. Retrieval contract: [config/sources.yaml](../config/sources.yaml). Raw snapshots: [data/raw-or-fixtures/sources/](../data/raw-or-fixtures/sources/).

## Providers

| Provider | Licence | Terms (verified) | API documentation |
|---|---|---|---|
| Eurostat | CC BY 4.0 | [Copyright notice](https://ec.europa.eu/eurostat/help/copyright-notice) | [API getting started](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/api) |
| World Bank (WDI) | CC BY 4.0 | [Public licenses](https://datacatalog.worldbank.org/public-licenses) | [Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation) |

Attribution required by both: "Source: Eurostat" / "Source: World Bank, World Development Indicators", shown in the dashboard.

## Indicators

| Indicator id | Lens | Dataset | Frequency | Unit | Series (filters) |
|---|---|---|---|---|---|
| `unemployment_rate` | Labour supply | [une_rt_m](https://ec.europa.eu/eurostat/databrowser/view/une_rt_m/default/table) | Monthly | % of labour force | SA, age TOTAL, sex T, PC_ACT |
| `job_vacancy_rate` | Labour demand | [jvs_q_r21](https://ec.europa.eu/eurostat/databrowser/view/jvs_q_r21/default/table) | Quarterly | % of occupied + vacant posts | NSA, JVR, NACE Rev. 2.1 B-T, all sizes |
| `hicp_inflation` | Cost of living | [prc_hicp_minr](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table) | Monthly | % change vs same month a year earlier | RCH_A, all items (TOTAL) |
| `hicp_inflation_first_release` | Cost of living | [prc_hicp_fpd](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_fpd/default/table) | Monthly | as above | RCH_A, TOTAL; `release` FIN and FLS kept |
| `economic_sentiment` | Economic cycle | [ei_bssi_m_r2](https://ec.europa.eu/eurostat/databrowser/view/ei_bssi_m_r2/default/table) | Monthly | Index, long-term average = 100 | BS-ESI-I, SA |
| `gdp_growth` | Economic cycle | [NY.GDP.MKTP.KD.ZG](https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG) | Annual | % change vs previous year | constant prices |

## Coverage and observed timeliness

Observed from the snapshots, not from release calendars. "Lag" = time from end of latest period to the provider's last update.

| Indicator | Coverage (all 6 countries) | Latest period | Provider updated | Observed lag |
|---|---|---|---|---|
| `unemployment_rate` | 2019-01 → 2026-07 | 2026-07 (IE: 2026-08) | 2026-09-22 | ~1.5–2 months; IE one month ahead |
| `job_vacancy_rate` | 2019-Q1 → 2026-Q2 | 2026-Q2 | 2026-09-15 | ~2.5 months |
| `hicp_inflation` | 2019-01 → 2026-08 | 2026-08 | 2026-09-17 | ~2.5 weeks |
| `hicp_inflation_first_release` | 2019-01 → 2026-08 | 2026-08 | 2026-09-17 | ~2.5 weeks (flash earlier) |
| `economic_sentiment` | 2019-01 → 2026-08; **IT missing 2020-04** (likely COVID survey disruption, unconfirmed; before the 2021 horizon) | 2026-08 | 2026-08-28 | published within the reference month |
| `gdp_growth` | 2019 → 2025 | 2025 | 2026-07-13 | ~6.5 months |

## Canonical mapping

- Country: ISO 3166-1 alpha-2 is canonical ([config/countries.yaml](../config/countries.yaml)). Eurostat uses `EL` for Greece; the World Bank uses ISO3 (`GRC`, `ROU`, `POL`, `ITA`, `IRL`, `BGR`).
- Period: provider period strings are kept as-is in source-shaped records (`2025-01`, `2025-Q1`, `2025`) and converted during curation, keeping the original period and frequency. No annual or quarterly value is presented as a monthly measurement.

## Decisions and limitations

| Topic | Decision / limitation |
|---|---|
| Dataset migrations | `jvs_q_nace2` is frozen at 2025-Q4 and `prc_hicp_manr` at 2025-12. We use their live successors, `jvs_q_r21` and `prc_hicp_minr`, whose dimensions were renamed (`nace_r2` → `nace_r2_1`, `coicop` → `coicop18`). The Eurostat adapter treats a missing or renamed filter dimension as a contract error. |
| Vacancy scope | B-T used because A-T (all activities) is absent for IE, EL and IT. Agriculture is excluded for all countries. |
| Vacancy seasonality | Only NSA requested. Compare like quarters or use year-on-year changes. |
| First-release inflation | `prc_hicp_fpd` keeps values as first published, so as-of joins cannot use later revisions. FLS (flash) values exist only for IE, EL, IT, and BG from 2026-01 (likely euro-area membership; to confirm in dataset metadata). The exact FIN semantics are to be confirmed in the Eurostat metadata. |
| Revisions elsewhere | Unemployment, vacancies, sentiment and GDP snapshots hold latest revised values, not the values known at the time. This is a documented look-ahead limitation. |
| Ireland GDP | Distorted by multinational accounting (2021 +16.3%, 2023 −2.5%, 2025 +12.3%). Used as annual context only; economic sentiment is the primary cycle indicator. |
| Missing values | Kept as gaps. Never interpolated in the source-shaped layer. |
