import json
import logging

import pytest

from asteria.observability import JsonFormatter, TextFormatter, configure_logging


def record(**extra: object) -> logging.LogRecord:
    fields = {"name": "asteria.ingest.runner", "levelname": "WARNING",
              "levelno": logging.WARNING, "msg": "retrying request"}  # fmt: skip
    rec = logging.makeLogRecord(fields)
    rec.__dict__.update(extra)
    return rec


def test_text_is_one_readable_line_with_key_values() -> None:
    line = TextFormatter(colour=False).format(
        record(attempt=2, indicator="gdp_growth", skipped=None)
    )
    assert "WARNING" in line and "ingest" in line and "retrying request" in line
    assert "attempt=2" in line and "indicator=gdp_growth" in line
    assert "skipped" not in line  # empty fields are left out
    assert "\033[" not in line  # no colour codes when not a terminal


def test_json_keeps_every_field_for_machines() -> None:
    entry = json.loads(JsonFormatter().format(record(attempt=2)))
    assert (
        entry["level"] == "warning" and entry["attempt"] == 2 and entry["msg"] == "retrying request"
    )


@pytest.mark.parametrize(("fmt", "formatter", "level"), [
    ("text", TextFormatter, logging.WARNING),
    ("json", JsonFormatter, logging.INFO),
    ("auto", JsonFormatter, logging.INFO),  # stderr is not a terminal under pytest
])  # fmt: skip
def test_format_and_default_level(fmt: str, formatter: type, level: int) -> None:
    configure_logging(None, fmt)  # type: ignore[arg-type]
    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, formatter)
    assert root.level == level
