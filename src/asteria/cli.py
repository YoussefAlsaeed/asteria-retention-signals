"""Command-line entry point.

`asteria run` is the one documented command for the core workflow. The stage commands
(`ingest`, `curate`) exist so each stage can be rerun and inspected on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Optional, TypeVar

import typer

from asteria import __version__
from asteria.analytics.pipeline import AnalyseError, AnalyseReport, run_analyse
from asteria.config import ConfigError, Mode
from asteria.context import Context, load_context
from asteria.curate.pipeline import CurateError, CurateReport, run_curate
from asteria.ingest.http import HttpFetcher
from asteria.ingest.raw_store import RawStore
from asteria.ingest.runner import IngestReport, run_ingest, write_run_manifest
from asteria.observability import configure_logging

T = TypeVar("T")

app = typer.Typer(help="Asteria retention signals pipeline.", no_args_is_help=True)

ModeOption = Annotated[
    Optional[str],  # noqa: UP045 - typer needs Optional here on 3.11
    typer.Option(help="live = call provider APIs; replay = use stored snapshots."),
]


@app.callback()
def main(
    log_level: Annotated[
        Optional[str],  # noqa: UP045
        typer.Option(help="DEBUG, INFO, WARNING, ERROR. Default: WARNING for text, INFO for JSON."),
    ] = None,
    log_format: Annotated[
        str,
        typer.Option(
            envvar="ASTERIA_LOG_FORMAT",
            help="auto (text in a terminal, JSON when piped), text, or json.",
        ),
    ] = "auto",
) -> None:
    """Asteria retention signals pipeline."""
    if log_format not in ("auto", "text", "json"):
        typer.secho(
            f"--log-format must be auto, text or json, got '{log_format}'", fg="red", err=True
        )
        raise typer.Exit(2)
    configure_logging(log_level.upper() if log_level else None, log_format)  # type: ignore[arg-type]


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def ingest(
    mode: ModeOption = None,
    only: Annotated[
        Optional[list[str]],  # noqa: UP045
        typer.Option("--only", help="Indicator id to ingest; repeatable."),
    ] = None,
) -> None:
    """Retrieve external indicators (live) or re-validate stored snapshots (replay)."""
    ctx = _load_context()
    if only:
        _guard_config(lambda: [ctx.catalogue.indicator(i) for i in only])
    if _ingest(ctx, _parse_mode(mode or ctx.settings.mode), only).failed:
        raise typer.Exit(1)


@app.command()
def curate() -> None:
    """Build the canonical layer and quality report from stored snapshots and starter data."""
    if _curate(_load_context()).gate_failures:
        raise typer.Exit(1)


@app.command()
def analyse() -> None:
    """Compute objective measures, point-in-time signals, and associations."""
    _analyse(_load_context())


@app.command()
def run(mode: ModeOption = None) -> None:
    """Core workflow: ingest (replay by default), curate, analyse."""
    ctx = _load_context()
    ingest_report = _ingest(ctx, _parse_mode(mode or ctx.settings.mode), None)
    # Curate still runs after a partial ingest failure: the previous snapshot of a failed
    # source is intact, and the quality report shows exactly what is available.
    curate_report = _curate(ctx)
    if curate_report.gate_failures:
        typer.secho("Analysis skipped: the quality gate failed.", fg="red", err=True)
        raise typer.Exit(1)
    _analyse(ctx)
    if ingest_report.failed:
        raise typer.Exit(1)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
) -> None:
    """Serve the API and dashboard at http://HOST:PORT (build data first with `asteria run`)."""
    import uvicorn

    from asteria.api.app import create_app

    typer.echo(f"Dashboard: http://{host}:{port}   API docs: http://{host}:{port}/docs")
    uvicorn.run(create_app(_load_context()), host=host, port=port, log_config=None)


def _load_context() -> Context:
    return _guard_config(load_context)


def _guard_config(load: Callable[[], T]) -> T:
    try:
        return load()
    except ConfigError as exc:
        typer.secho(f"Configuration error: {exc}", fg="red", err=True)
        raise typer.Exit(2) from exc


def _ingest(ctx: Context, mode: Mode, only: list[str] | None) -> IngestReport:
    fetcher = None
    if mode == "live":
        s = ctx.settings
        fetcher = HttpFetcher.create(s.http_timeout_seconds, s.http_max_attempts)
    store = RawStore(ctx.settings.raw_sources_dir)
    try:
        report = run_ingest(ctx.catalogue, ctx.countries, ctx.adapters, store, mode, fetcher, only)
    finally:
        if fetcher:
            fetcher.close()
    manifest = write_run_manifest(report, ctx.settings.runs_dir)
    _print_ingest(report)
    typer.echo(f"Run manifest: {manifest}")
    if report.failed:
        typer.secho(
            f"{len(report.failed)} of {len(report.outcomes)} indicators failed.", fg="red", err=True
        )
    return report


def _curate(ctx: Context) -> CurateReport:
    try:
        report = run_curate(
            ctx.settings.curated_dir,
            ctx.catalogue,
            ctx.countries,
            ctx.workforce,
            ctx.adapters,
            RawStore(ctx.settings.raw_sources_dir),
        )
    except CurateError as exc:
        typer.secho(f"Curate failed: {exc}", fg="red", err=True)
        raise typer.Exit(1) from exc
    _print_curate(report)
    return report


def _analyse(ctx: Context) -> AnalyseReport:
    try:
        report = run_analyse(ctx.settings.curated_dir, ctx.analysis, ctx.workforce, ctx.objectives)
    except AnalyseError as exc:
        typer.secho(f"Analyse failed: {exc}", fg="red", err=True)
        raise typer.Exit(1) from exc
    typer.echo("\nAnalyse")
    for h in report.headlines:
        rate = "-" if h.rate is None else f"{h.rate:.1%}"
        confidence = h.confidence or ""
        typer.echo(f"  {h.objective_id:24} {h.period}  {rate:>6}  {h.status:20} {confidence}")
    failed = [a for a in report.associations if a.note.startswith("model failed")]
    typer.echo(
        f"  associations fitted: {len(report.associations) - len(failed)}"
        f" of {len(report.associations)}"
    )
    typer.echo(f"  summary: {report.outputs['analysis_summary']}")
    return report


def _parse_mode(value: str) -> Mode:
    if value not in ("live", "replay"):
        typer.secho(f"--mode must be 'live' or 'replay', got '{value}'", fg="red", err=True)
        raise typer.Exit(2)
    return value  # type: ignore[return-value]


def _print_ingest(report: IngestReport) -> None:
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


def _print_curate(report: CurateReport) -> None:
    typer.echo("\nCurate")
    typer.echo(
        f"  workforce rows read {report.workforce_rows_read} -> employees {report.employees}"
        f" (measurable {report.measurable}, in country scope {report.in_country_scope})"
    )
    typer.echo(f"  external canonical values {report.external_values}")
    for rule in report.rules:
        if rule.rows_affected:
            colour = "red" if rule.severity == "error" else None
            typer.secho(f"  {rule.rows_affected:>5}  {rule.severity:15} {rule.rule_id}", fg=colour)
    for indicator in report.missing_indicators:
        typer.secho(f"  unavailable: {indicator}", fg="yellow")
    typer.echo(f"  report: {report.outputs['quality_report']}")
    if report.gate_failures:
        failed = ", ".join(r.rule_id for r in report.gate_failures)
        typer.secho(f"Quality gate failed: {failed}", fg="red", err=True)
