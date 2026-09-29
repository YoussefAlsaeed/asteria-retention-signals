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

## Publication lags: spot check against official release dates

Each value is treated as available from `period_end + lag_days` and is first **used** on the first day of the next month on or after that date. A lag is safe when every real release came out on or before that first-use date. Checked on 2026-09-29 against Eurostat news releases, the European Commission (DG ECFIN) survey press-release archive, and the World Bank data update log.

| Signal | Lag | Releases checked (reference period → release date, days after period end) | Worst case | Verdict |
|---|---:|---|---:|---|
| Unemployment | 62 | Dec 2022 → [1 Feb 2023](https://ec.europa.eu/eurostat/documents/2995521/15893630/3-01022023-BP-EN.pdf) (32); Jan 2023 → [2 Mar 2023](https://ec.europa.eu/eurostat/documents/2995521/16138291/3-02032023-BP-EN.pdf) (30); Feb 2023 → [31 Mar 2023](https://ec.europa.eu/eurostat/documents/2995521/16324762/3-31032023-BP-EN.pdf) (31); Mar 2023 → [3 May 2023](https://ec.europa.eu/eurostat/documents/2995521/16668052/3-03052023-AP-EN.pdf) (33); Apr 2023 → [1 Jun 2023](https://ec.europa.eu/eurostat/documents/2995521/16863929/3-01062023-BP-EN.pdf) (32); Dec 2023 → [1 Feb 2024](https://ec.europa.eu/eurostat/documents/2995521/18426688/3-01022024-BP-EN.pdf) (32) | 33 days | ✅ Safe, about 4 weeks of margin |
| Job vacancies | 90 | Q2 2023 → [14 Sep 2023](https://ec.europa.eu/eurostat/web/products-euro-indicators/w/3-14092023-ap) (76); Q3 2023 → [18 Dec 2023](https://ec.europa.eu/eurostat/en/web/products-euro-indicators/w/3-18122023-ap) (79)\*; Q4 2023 → [15 Mar 2024](https://ec.europa.eu/eurostat/web/products-euro-indicators/w/3-15032024-ap) (75)\* | 79 days | ✅ Safe |
| Inflation (HICP, full release) | **25** (was 20) | Jun 2023 → [19 Jul 2023](https://ec.europa.eu/eurostat/documents/2995521/17179282/2-19072023-AP-EN.pdf) (19); Jul 2023 → [18 Aug 2023](https://ec.europa.eu/eurostat/documents/2995521/17334860/2-18082023-AP-EN.pdf) (18); Jan 2023 → [23 Feb 2023](https://ec.europa.eu/eurostat/web/products-euro-indicators/w/2-23022023-AP) (23); Jan 2024 → [22 Feb 2024](https://ec.europa.eu/eurostat/en/web/products-euro-indicators/w/2-22022024-ap) (22); Feb 2024 → [18 Mar 2024](https://ec.europa.eu/eurostat/en/web/products-euro-indicators/w/2-18032024-ap) (18); Jan 2025 → [24 Feb 2025](https://ec.europa.eu/eurostat/web/products-euro-indicators/w/2-24022025-ap) (24); Dec 2025 → [19 Jan 2026](https://ec.europa.eu/eurostat/web/products-euro-indicators/w/2-19012026-ap) (19) | 24 days (January, annual weight update) | ⚠️ The 20-day lag was shorter than January releases. No value was used early, because first use is the next-but-one month, but the documented availability date was wrong. **Raised to 25.** |
| Economic sentiment | **10** (was 0) | 2023 monthly releases 27–30 of the reference month; **December surveys: 7 Jan 2021, 7 Jan 2022, 5/6 Jan 2023, 8 Jan 2024, 8 Jan 2025** ([press-release archive](https://economy-finance.ec.europa.eu/economic-forecast-and-surveys/business-and-consumer-surveys/download-business-and-consumer-survey-data/press-releases_en)) | 8 days (December) | ❌ **Leak with lag 0:** December values were used from 1 January, 5–8 days before publication, affecting 4,861 of 65,184 person-months and 145 of 1,808 new-hire cohort members. **Raised to 10.** Results barely changed (tracer OR 0.83 → 0.82, smallest q 0.46 → 0.53). |
| GDP growth (World Bank) | 200 | Year Y enters WDI in its July update: 2020 data on 1 Jul 2021, 2021 data on 1 Jul 2022, 2022 and 2023 data in July 2023/2024 (day not stated) ([WDI update log](https://datahelpdesk.worldbank.org/knowledgebase/articles/906522-data-updates-and-errata)); 2025 data present by 13 Jul 2026 (snapshot) | ~182–194 days | ✅ Safe: first use is 1 August |

\* Reference quarter inferred from the release date and Eurostat's quarterly schedule; the release title states only the rate.

Remaining limitation: one fixed lag per series. Ireland's unemployment is published about a month earlier than the others, so a per-country lag would be fresher for Ireland.

## Canonical mapping

- Country: ISO 3166-1 alpha-2 is canonical ([config/countries.yaml](../config/countries.yaml)). Eurostat uses `EL` for Greece; the World Bank uses ISO3 (`GRC`, `ROU`, `POL`, `ITA`, `IRL`, `BGR`).
- Period: provider period strings are kept as-is in source-shaped records (`2025-01`, `2025-Q1`, `2025`) and converted during curation, keeping the original period and frequency. No annual or quarterly value is presented as a monthly measurement.

## Decisions and limitations

| Topic | Decision / limitation |
|---|---|
| Dataset migrations | `jvs_q_nace2` is frozen at 2025-Q4 and `prc_hicp_manr` at 2025-12. We use their live successors, `jvs_q_r21` and `prc_hicp_minr`, whose dimensions were renamed (`nace_r2` → `nace_r2_1`, `coicop` → `coicop18`). The Eurostat adapter treats a missing or renamed filter dimension as a contract error. |
| Vacancy scope | B-T used because A-T (all activities) is absent for IE, EL and IT. Agriculture is excluded for all countries. |
| Vacancy seasonality | Only NSA requested. Compare like quarters or use year-on-year changes. |
| First-release inflation | `prc_hicp_fpd` keeps values as first published, so as-of joins cannot use later revisions. **Checked: 0 of 360 country-months (2021–2025) differ from the revised `prc_hicp_minr`, so HICP is effectively unrevised and this safeguard makes no difference here** (checked 2026-09-28 by comparing the two curated series). FLS (flash) values exist only for IE, EL, IT, and BG from 2026-01 (likely euro-area membership; to confirm in dataset metadata). The exact FIN semantics are to be confirmed in the Eurostat metadata. |
| Revisions elsewhere | Unemployment, vacancies, sentiment and GDP snapshots hold latest revised values, not the values known at the time. This is a documented look-ahead limitation. |
| Ireland GDP | Distorted by multinational accounting (2021 +16.3%, 2023 −2.5%, 2025 +12.3%). Used as annual context only; economic sentiment is the primary cycle indicator. |
| Missing values | Kept as gaps, never interpolated. Gaps inside a series are reported by `EX_PERIOD_GAP`. |
| Provider status flags | Labels are taken from each payload's own `extension.status.label`, not assumed. Found: **Italy job vacancies flagged `d` "definition differs (see metadata)" for every quarter 2019-Q1 to 2025-Q4**, so Italy's vacancy level is not directly comparable with other countries; `p` "provisional" on recent vacancy quarters (BG, IE, IT); `e` "estimated" on 2026 first-release inflation. Flags are kept per value (`status`, `status_label`). |
