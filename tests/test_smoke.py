from typer.testing import CliRunner

from asteria import __version__
from asteria.cli import app


def test_cli_reports_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
