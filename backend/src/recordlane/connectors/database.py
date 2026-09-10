# SPDX-License-Identifier: Apache-2.0
"""Bounded PostgreSQL extraction and explicitly configured controlled writes."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, inspect, text

SAFE_READ = re.compile(r"^\s*select\b", re.IGNORECASE)
SAFE_WRITE = re.compile(r"^\s*(insert|update)\b", re.IGNORECASE)


def _single_statement(statement: str, pattern: re.Pattern[str]) -> None:
    if not pattern.match(statement) or ";" in statement or "--" in statement or "/*" in statement:
        raise ValueError("connector statement is outside the configured operation boundary")


class PostgreSQLConnector:
    def __init__(self, database_url: str, *, batch_size: int = 1_000):
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("PostgreSQL connector requires a PostgreSQL URL")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.batch_size = batch_size

    def test_connection(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def discover(self, schema: str = "public") -> dict[str, list[dict[str, Any]]]:
        inspector = inspect(self.engine)
        return {
            table: inspector.get_columns(table, schema=schema)
            for table in inspector.get_table_names(schema=schema)
        }

    def read(self, statement: str, parameters: dict | None = None) -> Iterator[dict[str, Any]]:
        _single_statement(statement, SAFE_READ)
        with self.engine.connect().execution_options(stream_results=True) as connection:
            result = connection.execute(text(statement), parameters or {})
            while rows := result.mappings().fetchmany(self.batch_size):
                yield from (dict(row) for row in rows)

    def publish(self, statement: str, values: dict[str, Any]) -> int:
        """Execute an administrator-supplied INSERT/UPDATE with bound values only."""

        _single_statement(statement, SAFE_WRITE)
        if "event_id" not in values:
            raise ValueError("controlled publication requires an event_id for echo suppression")
        with self.engine.begin() as connection:
            return connection.execute(text(statement), values).rowcount
