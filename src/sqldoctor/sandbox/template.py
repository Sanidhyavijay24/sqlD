"""
@file template.py
@description PostgreSQL template database manager for fast ephemeral database cloning
@module sqldoctor/sandbox/template
"""

import psycopg
from psycopg import sql

from sqldoctor.config import SandboxConfig


class TemplateDBError(Exception):
    """Raised when template database creation or cloning operations fail."""


class TemplateDatabaseManager:
    """Manages creation of template databases and fast per-test clones."""

    def __init__(self, config: SandboxConfig) -> None:
        """Initialize with SandboxConfig.

        Args:
            config: SandboxConfig defining connection credentials and timeouts.
        """
        self.config = config

    def _get_admin_uri(self) -> str:
        """Return connection URI to default administrative postgres database."""
        return (
            f"postgresql://{self.config.user}:{self.config.password}"
            f"@localhost:{self.config.port}/postgres"
        )

    def get_db_uri(self, db_name: str) -> str:
        """Return connection URI for a specific database name."""
        return (
            f"postgresql://{self.config.user}:{self.config.password}"
            f"@localhost:{self.config.port}/{db_name}"
        )

    def create_template(self, template_name: str, ddl_sql: str) -> None:
        """Create a template database and apply schema DDL.

        Args:
            template_name: Unique identifier for the template.
            ddl_sql: DDL statements creating tables, constraints, and indexes.
        """
        # Ensure template is dropped if it already exists
        self.drop_database(template_name)

        # 1. Create fresh database
        with psycopg.connect(self._get_admin_uri(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(template_name)))

        # 2. Apply DDL inside template
        with psycopg.connect(self.get_db_uri(template_name)) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl_sql)
            conn.commit()

        # 3. Mark database as template to allow cloning
        with psycopg.connect(self._get_admin_uri(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("ALTER DATABASE {} WITH is_template true").format(
                        sql.Identifier(template_name)
                    )
                )

    def clone_from_template(self, clone_name: str, template_name: str) -> str:
        """Instantly clone a database from the template.

        Args:
            clone_name: Name for the ephemeral cloned database.
            template_name: Name of the existing template database.

        Returns:
            Connection URI for the cloned database.
        """
        self.drop_database(clone_name)

        with psycopg.connect(self._get_admin_uri(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                        sql.Identifier(clone_name), sql.Identifier(template_name)
                    )
                )

        return self.get_db_uri(clone_name)

    def drop_database(self, db_name: str) -> None:
        """Drop a database, terminating existing connections if necessary.

        Args:
            db_name: Name of the database to drop.
        """
        try:
            with psycopg.connect(self._get_admin_uri(), autocommit=True) as conn:
                with conn.cursor() as cur:
                    # Terminate other sessions connected to this database
                    cur.execute(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = %s AND pid <> pg_backend_pid();
                        """,
                        (db_name,),
                    )
                    # Disallow template status if previously marked
                    cur.execute(
                        """
                        SELECT 1 FROM pg_database WHERE datname = %s AND datistemplate;
                        """,
                        (db_name,),
                    )
                    if cur.fetchone():
                        cur.execute(
                            sql.SQL("ALTER DATABASE {} WITH is_template false").format(
                                sql.Identifier(db_name)
                            )
                        )
                    cur.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name))
                    )
        except Exception as exc:
            raise TemplateDBError(f"Failed to drop database '{db_name}': {exc}") from exc
