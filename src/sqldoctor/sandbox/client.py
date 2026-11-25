"""
@file client.py
@description Database client and query execution helper for the sandbox
@module sqldoctor/sandbox/client
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg

from sqldoctor.config import SandboxConfig


class SandboxClient:
    """Manages connections, timeouts, and transactional execution inside the sandbox."""

    def __init__(self, config: SandboxConfig) -> None:
        """Initialize client with sandbox configuration.

        Args:
            config: SandboxConfig defining connection credentials and timeouts.
        """
        self.config = config

    @property
    def connection_uri(self) -> str:
        """PostgreSQL connection URI."""
        return (
            f"postgresql://{self.config.user}:{self.config.password}"
            f"@localhost:{self.config.port}/{self.config.database}"
        )

    @contextmanager
    def connect(self) -> Generator[psycopg.Connection, None, None]:
        """Context manager providing an active connection with timeout."""
        with psycopg.connect(self.connection_uri) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {self.config.statement_timeout_ms};")
            yield conn

    def execute_query(
        self, sql: str, params: tuple[Any, ...] | None = None
    ) -> list[tuple[Any, ...]]:
        """Execute a query and return all fetched rows.

        Args:
            sql: SQL query string.
            params: Optional tuple of query parameters.

        Returns:
            List of row tuples.
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchall()
                conn.commit()
                return []

    def execute_script(self, script_sql: str) -> None:
        """Execute a multi-statement SQL script.

        Args:
            script_sql: SQL script containing multiple DDL/DML statements.
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(script_sql)
            conn.commit()
