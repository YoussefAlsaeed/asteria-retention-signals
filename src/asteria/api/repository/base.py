"""Connection handling shared by every query group.

Each call opens a short read-only DuckDB connection, so the API never holds a lock that
would block `asteria run` from rebuilding the file, and every query is parameterised.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

REQUIRED_TABLES = {
    "employees",
    "external_coverage",
    "external_observations",
    "mart_objective_measures",
    "mart_signal_asof",
    "mart_association_results",
    "mart_association_cells",
    "cfg_rules",
    "wf_quality_events",
    "ex_quality_events",
}


class DataNotReady(Exception):
    """The analytical product has not been built (or is incomplete)."""


class BaseRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if not self.db_path.exists():
            raise DataNotReady(f"{self.db_path.name} not found")
        try:
            con = duckdb.connect(str(self.db_path), read_only=True)
        except duckdb.IOException as exc:  # e.g. locked while `asteria run` rebuilds it
            raise DataNotReady(f"database unavailable: {exc}") from exc
        try:
            yield con
        finally:
            con.close()

    def _rows(self, query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        with self._connect() as con:
            try:
                cursor = con.execute(query, params or [])
            except duckdb.CatalogException as exc:
                raise DataNotReady(f"analytical tables missing: {exc}") from exc
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def missing_tables(self) -> set[str]:
        rows = self._rows("SELECT table_name FROM information_schema.tables")
        return REQUIRED_TABLES - {r["table_name"] for r in rows}
