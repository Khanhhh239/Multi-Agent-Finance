from __future__ import annotations

from pathlib import Path

import duckdb

from .compiler import assert_safe_select
from .errors import DataUnavailable, UnsafeQuery
from .models import BoundQuery, ResultColumn, ResultData, decimal_string


class DuckDBReadOnlyExecutor:
    """A fresh read-only connection per request avoids leaked session state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def ready(self) -> bool:
        if not self.database_path.is_file():
            return False
        try:
            with duckdb.connect(str(self.database_path), read_only=True) as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except duckdb.Error:
            return False

    def execute(self, query: BoundQuery) -> tuple[ResultData, str | None]:
        assert_safe_select(query.sql)
        if not self.database_path.is_file():
            raise DataUnavailable("synthetic database is unavailable")
        try:
            with duckdb.connect(str(self.database_path), read_only=True) as connection:
                cursor = connection.execute(query.sql, list(query.params))
                description = cursor.description or []
                raw_rows = cursor.fetchall()
                watermark_row = connection.execute(
                    "SELECT value FROM company_info WHERE key='as_of_date'"
                ).fetchone()
        except duckdb.Error as exc:
            raise DataUnavailable("read-only query execution failed") from exc
        truncated = len(raw_rows) > query.row_cap
        raw_rows = raw_rows[: query.row_cap]
        names = [item[0] for item in description]
        if len(set(names)) != len(names):
            raise UnsafeQuery("duplicate result columns")
        rows = [
            {name: decimal_string(value) for name, value in zip(names, row, strict=True)}
            for row in raw_rows
        ]
        columns = []
        for name in names:
            sample = next((row[name] for row in rows if row[name] is not None), None)
            if name in query.units:
                column_type = "decimal"
            elif isinstance(sample, bool):
                column_type = "boolean"
            elif isinstance(sample, int):
                column_type = "integer"
            else:
                column_type = "string"
            columns.append(ResultColumn(key=name, type=column_type, unit=query.units.get(name)))
        return ResultData(columns=columns, rows=rows, row_count=len(rows), truncated=truncated), (
            watermark_row[0] if watermark_row else None
        )
