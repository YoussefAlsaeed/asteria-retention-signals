# Asteria Retention Signals

External labour-market and macroeconomic signals × workforce retention for Asteria Consumer Products (fictional).

An agentic engineering assessment (software emphasis): a reproducible vertical slice from public-source research through ingestion, curation, retention analytics, temporal integration, and an accessible interactive dashboard.

## Quick start (reviewers)

You need only **git** and **[uv](https://docs.astral.sh/uv/)**, which also installs Python 3.11+ if it is missing. No accounts, API keys, or paid services: everything runs offline from the committed data.

```sh
# 1. Get the code
git clone https://github.com/YoussefAlsaeed/asteria-retention-signals.git
cd asteria-retention-signals

# 2. Install uv (skip if `uv --version` works)
#    macOS / Linux:        curl -LsSf https://astral.sh/uv/install.sh | sh
#    Windows PowerShell:   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 3. Install the locked dependencies into .venv
uv sync

# 4. Build everything: ingest (offline replay) -> curate -> analyse
uv run asteria run

# 5. Open the dashboard at http://127.0.0.1:8000   (Ctrl+C to stop)
uv run asteria serve
```

Step 4 takes about 20 seconds and prints a summary per stage. Outputs land in `data/curated/`: the quality report, analysis summary, and CSV exports. Reruns give byte-identical results.

Optional checks:

```sh
uv run python scripts/verify_findings.py   # recompute every finding independently (107 checks)
uv run playwright install chromium          # once, for the browser tests
uv run pytest                               # unit, SQL, API and browser tests
uv run asteria ingest --mode live           # refresh from Eurostat / World Bank (needs internet)
```

Where to look next: [docs/findings.md](docs/findings.md) (results), [docs/analysis_explained.md](docs/analysis_explained.md) (method for engineers), [docs/source_register.md](docs/source_register.md) (sources, licences, lags), [AI_USAGE.md](AI_USAGE.md).

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```sh
uv sync            # create the virtualenv and install locked dependencies
uv run pytest      # run the test suite
uv run ruff check  # lint
uv run mypy        # strict type check
# Python 3.11 compatibility (the minimum supported version):
uv run --python 3.11 --isolated --with-editable . --with pytest --with httpx pytest -q
uv run asteria --help
```

## Core workflow

```sh
uv run asteria run                  # ingest (offline replay) + curate + analyse: one command
```

Stages can also be run alone:

```sh
uv run asteria ingest               # replay committed snapshots (offline, deterministic)
uv run asteria ingest --mode live   # call Eurostat and World Bank, refresh snapshots
uv run asteria curate               # rebuild the canonical layer and quality report
uv run asteria analyse              # objective measures, point-in-time signals, associations
```

### Data layers

| Layer | Where | Contents |
|---|---|---|
| Raw | `data/raw-or-fixtures/starter/`, `data/raw-or-fixtures/sources/` | Supplied CSVs and byte-exact API payloads with checksummed metadata |
| Source-shaped | DuckDB `raw_workforce`, `stg_external` | Provider codes and period strings, untyped |
| Canonical | DuckDB `employees`, `external_observations`, `external_coverage` | ISO countries, real period bounds, typed values, quality flags, lineage |
| Analytical product | DuckDB `mart_objective_measures`, `mart_signal_asof`, `mart_association_*` | Objective rates with Wilson intervals and status per country x segment x period; signals as known at each month |
| Evidence | `data/curated/*.csv`, `quality_report.md`, `analysis_summary.md` | Deterministic exports; reruns are byte-identical |

Metric definitions and as-of rules: [config/analysis.yaml](config/analysis.yaml). Findings (draft): [docs/findings.md](docs/findings.md); how they were produced, for engineers: [docs/analysis_explained.md](docs/analysis_explained.md). Recompute every finding independently: `uv run python scripts/verify_findings.py`.

The DuckDB file (`data/curated/asteria.duckdb`) is rebuilt from scratch on every curate run and is not committed. Transformations are plain SQL in `src/asteria/curate/sql/`; rule definitions and severities are in `src/asteria/curate/quality.py`; correction rules (aliases, allowed values, as-of date) in `config/workforce.yaml`. A rule with severity `error` fails the run (quality gate).

## Dashboard

```sh
uv run asteria run      # build the data (once)
uv run asteria serve    # then open http://127.0.0.1:8000  (API reference: /docs)
```

| View | What it shows |
|---|---|
| Explore | One filter row scoping everything: objective, country, business unit, period grain, definition (main or sensitivity), external signal. Kept in the URL. |
| Understand | Objective trend with 95% interval and target line; the selected signal as known each month, as a separate chart (different units, never a dual axis) |
| Challenge | Country-quarter scatter sized by sample; naive vs within-country association table with q-values and a plain-language verdict |
| Trust | Freshness, coverage, provider flags, quality rules with affected rows, definitions, sources and licences |

Plain HTML/JS/SVG served by FastAPI: no build step, no CDN, works offline. Accessibility: keyboard-readable charts (arrow keys, announced through an aria-live region), a table view for every chart, status shown with icon and text (never colour alone), light and dark themes with a colour-blind-validated palette, and graceful loading, empty, pending, "not built" and "API unreachable" states. Screenshots: [docs/screenshots/](docs/screenshots/).

## Tests

```sh
uv run playwright install chromium   # once, for the browser tests
uv run pytest                        # unit, SQL, API, and browser (Playwright + axe) tests
```

## External data ingest

Logs go to stderr: readable text in a terminal (warnings and errors only; add `--log-level INFO` for every step), and JSON at INFO when piped or run by a scheduler. Force either with `--log-format text|json` or `ASTERIA_LOG_FORMAT`.

Live runs validate each payload before storing it, leave unchanged snapshots untouched, and keep the previous snapshot if a source fails. Exit code 1 means at least one indicator failed; details are in the summary, the JSON logs on stderr, and `data/runs/ingest_<run_id>.json`. Sources and their limitations: [docs/source_register.md](docs/source_register.md).

## Repository layout

| Path | Contents |
|---|---|
| `src/asteria/` | Python package: `domain/`, `sources/`, `ingest/`, `curate/`, `analytics/`, `api/`, `cli.py` |
| `config/` | Indicator, country, lag, and objective configuration |
| `data/raw-or-fixtures/` | Supplied starter pack (`starter/`) and recorded API payloads for offline replay |
| `data/curated/` | Canonical and analytical outputs |
| `dashboard/` | Interactive insight experience |
| `tests/` | Unit, contract, API, and UI tests |
| `docs/` | Assessment brief, requirements refinement, source register, architecture |
| `presentation/` | Interview deck |
| `AI_USAGE.md` | How the AI coding agent was directed and verified |

All company, employee, event, and target data in this repository is synthetic.
