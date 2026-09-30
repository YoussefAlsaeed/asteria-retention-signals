# Architecture: local build and production mapping

The assessment runs locally with free tools. This page shows how each local part maps to an Azure production setup (ADF-style orchestration, a Databricks lakehouse, Power BI). The production column is a **design proposal**, not something that was built.

## Local architecture (what exists)

```
config/*.yaml ──► asteria run
                    │
   ┌────────────────┼──────────────────────────────────────────────┐
   │ ingest         │ curate                   │ analyse            │ serve
   │ sources/*.py   │ curate/sql/*.sql         │ analytics/sql/*.sql│ api/ + dashboard/
   │ adapters,      │ 23 quality rules,        │ objectives, as-of  │ FastAPI (read-only)
   │ retries,       │ canonical tables,        │ join, logistic     │ HTML/SVG dashboard
   │ raw snapshots  │ quality gate             │ models             │
   └───────┬────────┴────────────┬─────────────┴─────────┬──────────┘
           ▼                     ▼                       ▼
  data/raw-or-fixtures/   DuckDB: employees,      DuckDB: mart_* tables
  (byte-exact + sha256)   external_observations   + CSV evidence exports
```

| Layer | Local | Contents |
|---|---|---|
| Raw (bronze) | `data/raw-or-fixtures/` | Starter CSVs and API payloads, byte-exact, with checksummed metadata |
| Canonical (silver) | DuckDB `employees`, `external_observations` | ISO countries, real period dates, quality flags, lineage columns |
| Analytical product (gold) | DuckDB `mart_*` | Objective measures with intervals, point-in-time signals, association results |

## Production mapping

| Concern | Local | Production (proposal) |
|---|---|---|
| **Orchestration** | `asteria run` (one command, stages in order) | **ADF pipeline**: an Ingest activity, then Curate and Analyse as Databricks job activities, then a Power BI dataset refresh. A failed activity stops the downstream ones. |
| **Scheduling** | Manual | ADF **schedule trigger** monthly, a few days after the latest release in the source register (e.g. the 20th), plus an **event trigger** when a new HR extract lands in storage. The publication-lag rule means an early run can never use data too soon. |
| **Ingestion** | `sources/` adapters with retries, contract checks, raw snapshots | The same Python package, installed as a **wheel on a Databricks job cluster**, writing raw payloads to the bronze container. ADF Copy activities are an alternative, but would lose the contract checks. |
| **Storage** | Files + a DuckDB file | **ADLS Gen2** with bronze/silver/gold containers as **Delta tables** registered in **Unity Catalog**. Bronze is append-only, versioned by fetch time and checksum. |
| **Transformations** | DuckDB SQL files | The same SQL, run as **Spark SQL / Databricks SQL**. The logic is standard SQL; DuckDB-specific parts (`ASOF JOIN`, macros) are rewritten as window-function joins and SQL UDFs. The quality gate becomes a failing task. |
| **Secrets** | None needed (public APIs, local files) | **Azure Key Vault**, reached through **managed identities**: ADF linked services and Databricks secret scopes backed by Key Vault. HR system credentials never live in code or config. |
| **Observability** | JSON logs, run manifest, quality report | JSON logs go to **Log Analytics** (the formatter already emits JSON when not interactive). The run manifest and quality report become **Delta tables**. **Azure Monitor alerts** fire on pipeline failure, the quality gate, or stale sources, to email or Teams. |
| **Consumption** | FastAPI + HTML dashboard | **Power BI** semantic model on the gold tables through a **Databricks SQL warehouse**. The four dashboard views become report pages; intervals and status are precomputed in gold, not in DAX. |
| **Access control** | Local only | **Unity Catalog grants**: HR person-level tables (silver) restricted to the data team; gold aggregates for analysts. **Power BI row-level security** by country for country managers. **Entra ID groups** throughout. |
| **Promotion** | Git branch | **Dev → Test → Prod** workspaces. ADF Git integration with ARM/Bicep templates; **Databricks Asset Bundles** for jobs; a CI pipeline (GitHub Actions or Azure DevOps) runs `ruff`, `mypy` and `pytest` on every pull request, then deploys by environment. Only config differs between environments (storage paths, Key Vault names). |

## What carries over unchanged

- **Adapters, domain rules and SQL:** the business logic is independent of DuckDB and FastAPI.
- **Config files:** indicators, lags, objectives and quality rules become environment-agnostic config.
- **Tests:** the SQL tests run against a small Spark session in CI; replay fixtures keep them network-free.

## What would change for real HR data

- **Personal data:** the silver `employees` table is personal data. It needs restricted access, a retention policy, pseudonymised IDs in gold, and no person-level rows in Power BI.
- **Incremental loads:** HR extracts arrive monthly, so the silver layer becomes a `MERGE` (upsert) on `employee_id` + `record_updated_at` instead of a full rebuild. The current full rebuild is intentional at 2,400 rows.
