"""Logging to stderr: readable text for people, structured JSON for machines.

`auto` picks text when stderr is an interactive terminal and JSON otherwise (piped output,
CI, a scheduler capturing logs), so production log collection needs no extra flag.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Literal

LogFormat = Literal["auto", "text", "json"]

# Attributes every LogRecord has; anything else was passed via `extra=` and is logged.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _extras(record: logging.LogRecord) -> dict[str, object]:
    return {k: v for k, v in vars(record).items() if k not in _STANDARD}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry |= _extras(record)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class TextFormatter(logging.Formatter):
    """`12:04:31  INFO   ingest   indicator ingested  indicator=gdp_growth status=ok`"""

    COLOURS = {"WARNING": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m"}
    RESET, DIM = "\033[0m", "\033[2m"

    def __init__(self, colour: bool) -> None:
        super().__init__()
        self.colour = colour

    def format(self, record: logging.LogRecord) -> str:
        time = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        stage = record.name.removeprefix("asteria.").split(".")[0]
        fields = "  ".join(f"{k}={v}" for k, v in _extras(record).items() if v is not None)
        level = f"{record.levelname:<7}"
        if self.colour:
            level = f"{self.COLOURS.get(record.levelname, '')}{level}{self.RESET}"
            fields = f"{self.DIM}{fields}{self.RESET}" if fields else ""
        line = f"{time}  {level}{stage:<10} {record.getMessage()}"
        if fields:
            line += f"  {fields}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str | None = None, log_format: LogFormat = "auto") -> None:
    """Text defaults to WARNING (the CLI prints its own summaries); JSON defaults to INFO."""
    interactive = sys.stderr.isatty()
    use_json = log_format == "json" or (log_format == "auto" and not interactive)
    level = level or ("INFO" if use_json else "WARNING")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if use_json else TextFormatter(colour=interactive))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # httpx logs every request at INFO; our own logs already carry the outcome.
    logging.getLogger("httpx").setLevel(logging.WARNING)
