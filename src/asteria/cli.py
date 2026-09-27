"""Command-line entry point. Pipeline commands are added as each stage lands."""

import typer

from asteria import __version__

app = typer.Typer(help="Asteria retention signals pipeline.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.callback()
def main() -> None:
    """Asteria retention signals pipeline."""
