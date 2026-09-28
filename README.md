# Asteria Retention Signals

External labour-market and macroeconomic signals × workforce retention for Asteria Consumer Products (fictional).

An agentic engineering assessment (software emphasis): a reproducible vertical slice from public-source research through ingestion, curation, retention analytics, temporal integration, and an accessible interactive dashboard.

> Status: work in progress. Pipeline and dashboard instructions will be added as each stage lands.

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```sh
uv sync            # create the virtualenv and install locked dependencies
uv run pytest      # run the test suite
uv run ruff check  # lint
uv run asteria --help
```

## External data ingest

```sh
uv run asteria ingest               # replay committed snapshots (offline, deterministic)
uv run asteria ingest --mode live   # call Eurostat and World Bank, refresh snapshots
uv run asteria ingest --only unemployment_rate
```

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
