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
