"""Command-line entry point. Pipeline commands are added as each stage lands."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from asteria import __version__
from asteria.config import ConfigError, Mode, Settings, load_countries, load_sources
from asteria.ingest.http import HttpFetcher
from asteria.ingest.raw_store import RawStore
from asteria.ingest.runner import IngestReport, run_ingest, write_run_manifest
from asteria.observability import configure_logging
from asteria.sources import build_adapters

app = typer.Typer(help="Asteria retention signals pipeline.", no_args_is_help=True)


@app.callback()
def main(
    log_level: Annotated[str, typer.Option(help="Log level for JSON logs on stderr.")] = "INFO",
) -> None:
    """Asteria retention signals pipeline."""
    configure_logging(log_level.upper())


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def ingest(
    mode: Annotated[
        Optional[str],  # noqa: UP045 - typer needs Optional here on 3.11
        typer.Option(help="live = call provider APIs; replay = use stored snapshots."),
    ] = None,
    only: Annotated[
        Optional[list[str]],  # noqa: UP045
        typer.Option("--only", help="Indicator id to ingest; repeatable."),
    ] = None,
) -> None:
    """Retrieve external indicators (live) or re-validate stored snapshots (replay)."""
    settings = Settings()
    run_mode: Mode = _parse_mode(mode or settings.mode)
    try:
        catalogue = load_sources(settings.config_dir)
        countries = load_countries(settings.config_dir)
        adapters = build_adapters(catalogue)
        if only:
            for indicator_id in only:
                catalogue.indicator(indicator_id)
    except ConfigError as exc:
        typer.secho(f"Configuration error: {exc}", fg="red", err=True)
        raise typer.Exit(2) from exc

    fetcher = None
    if run_mode == "live":
        fetcher = HttpFetcher.create(settings.http_timeout_seconds, settings.http_max_attempts)
    try:
        report = run_ingest(
            catalogue,
            countries,
            adapters,
            RawStore(settings.raw_sources_dir),
            run_mode,
            fetcher,
            only,
        )
    finally:
        if fetcher:
            fetcher.close()

    manifest = write_run_manifest(report, settings.runs_dir)
    _print_summary(report)
    typer.echo(f"Run manifest: {manifest}")
    if report.failed:
        typer.secho(
            f"{len(report.failed)} of {len(report.outcomes)} indicators failed.", fg="red", err=True
        )
        raise typer.Exit(1)


def _parse_mode(value: str) -> Mode:
    if value not in ("live", "replay"):
        typer.secho(f"--mode must be 'live' or 'replay', got '{value}'", fg="red", err=True)
        raise typer.Exit(2)
    return value  # type: ignore[return-value]


def _print_summary(report: IngestReport) -> None:
    typer.echo(f"\nIngest {report.run_id} ({report.mode})")
    typer.echo(f"{'indicator':32} {'status':7} {'change':10} {'obs':>5}  geos  source updated")
    for o in report.outcomes:
        colour = "green" if o.status == "ok" else "red"
        line = (
            f"{o.indicator_id:32} {o.status:7} {o.change or '-':10} {o.observations:>5}  "
            f"{len(o.coverage):>4}  {(o.source_updated or '-')[:19]}"
        )
        typer.secho(line, fg=colour)
        for warning in o.warnings:
            typer.secho(f"{'':34}warning: {warning}", fg="yellow")
        if o.error:
            typer.secho(f"{'':34}{o.error_type}: {o.error}", fg="red")
