"""
@file loader.py
@description Extracts PostgreSQL schema objects directly from system catalogs
@module sqldoctor/schema/loader
"""

import psycopg

from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    IndexModel,
    SchemaModel,
    TableModel,
)


class SchemaLoader:
    """Loads database schema directly from PostgreSQL pg_catalog."""

    def __init__(self, connection_uri: str) -> None:
        """Initialize loader with database connection URI.

        Args:
            connection_uri: Connection string for PostgreSQL instance.
        """
        self.connection_uri = connection_uri

    def load_schema(self, schema_name: str = "public") -> SchemaModel:
        """Extract all tables, columns, constraints and indexes for the schema.

        Args:
            schema_name: Target PostgreSQL schema name (default 'public').

        Returns:
            SchemaModel containing all extracted metadata.
        """
        tables: dict[str, TableModel] = {}

        with psycopg.connect(self.connection_uri) as conn:
            with conn.cursor() as cur:
                # 1. Fetch all base tables in schema
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                    """,
                    (schema_name,),
                )
                table_names = [row[0] for row in cur.fetchall()]

                for tbl_name in table_names:
                    # 2. Fetch columns for table
                    cur.execute(
                        """
                        SELECT
                            column_name,
                            data_type,
                            is_nullable,
                            column_default,
                            character_maximum_length,
                            numeric_precision,
                            numeric_scale
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position;
                        """,
                        (schema_name, tbl_name),
                    )
                    columns: dict[str, ColumnModel] = {}
                    for col in cur.fetchall():
                        (
                            c_name,
                            d_type,
                            is_null,
                            c_def,
                            char_max,
                            num_prec,
                            num_scale,
                        ) = col
                        columns[c_name] = ColumnModel(
                            name=c_name,
                            data_type=d_type,
                            is_nullable=(is_null.upper() == "YES"),
                            column_default=c_def,
                            character_maximum_length=char_max,
                            numeric_precision=num_prec,
                            numeric_scale=num_scale,
                        )

                    # 3. Fetch constraints from pg_catalog
                    cur.execute(
                        """
                        SELECT
                            con.conname AS constraint_name,
                            con.contype AS constraint_type,
                            pg_get_constraintdef(con.oid, true) AS definition,
                            ARRAY(
                                SELECT att.attname
                                FROM unnest(con.conkey) WITH ORDINALITY
                                    AS k(attnum, ord)
                                JOIN pg_attribute att
                                    ON att.attrelid = con.conrelid
                                    AND att.attnum = k.attnum
                                ORDER BY k.ord
                            ) AS columns,
                            f_cls.relname AS foreign_table,
                            ARRAY(
                                SELECT f_att.attname
                                FROM unnest(con.confkey) WITH ORDINALITY
                                    AS fk(attnum, ord)
                                JOIN pg_attribute f_att
                                    ON f_att.attrelid = con.confrelid
                                    AND f_att.attnum = fk.attnum
                                ORDER BY fk.ord
                            ) AS foreign_columns
                        FROM pg_constraint con
                        JOIN pg_class cls ON cls.oid = con.conrelid
                        JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
                        LEFT JOIN pg_class f_cls ON f_cls.oid = con.confrelid
                        WHERE nsp.nspname = %s AND cls.relname = %s;
                        """,
                        (schema_name, tbl_name),
                    )
                    constraints: list[ConstraintModel] = []
                    for con_row in cur.fetchall():
                        (
                            con_name,
                            con_type_code,
                            con_def,
                            con_cols,
                            f_table,
                            f_cols,
                        ) = con_row

                        c_type: ConstraintType
                        check_clause: str | None = None

                        if con_type_code == "p":
                            c_type = ConstraintType.PRIMARY_KEY
                        elif con_type_code == "f":
                            c_type = ConstraintType.FOREIGN_KEY
                        elif con_type_code == "u":
                            c_type = ConstraintType.UNIQUE
                        elif con_type_code == "c":
                            c_type = ConstraintType.CHECK
                            check_clause = con_def
                        else:
                            continue

                        constraints.append(
                            ConstraintModel(
                                name=con_name,
                                type=c_type,
                                columns=list(con_cols or []),
                                foreign_table=f_table,
                                foreign_columns=list(f_cols or []),
                                check_clause=check_clause,
                            )
                        )

                    # 4. Fetch indexes from pg_catalog
                    cur.execute(
                        """
                        SELECT
                            i_cls.relname AS index_name,
                            idx.indisunique AS is_unique,
                            idx.indisprimary AS is_primary,
                            am.amname AS method,
                            pg_get_indexdef(idx.indexrelid) AS definition,
                            ARRAY(
                                SELECT att.attname
                                FROM unnest(idx.indkey) WITH ORDINALITY
                                    AS k(attnum, ord)
                                JOIN pg_attribute att
                                    ON att.attrelid = cls.oid
                                    AND att.attnum = k.attnum
                                ORDER BY k.ord
                            ) AS columns
                        FROM pg_index idx
                        JOIN pg_class cls ON cls.oid = idx.indrelid
                        JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
                        JOIN pg_class i_cls ON i_cls.oid = idx.indexrelid
                        JOIN pg_am am ON am.oid = i_cls.relam
                        WHERE nsp.nspname = %s AND cls.relname = %s;
                        """,
                        (schema_name, tbl_name),
                    )
                    indexes: list[IndexModel] = []
                    for idx_row in cur.fetchall():
                        (
                            idx_name,
                            is_uniq,
                            is_prim,
                            idx_method,
                            idx_def,
                            idx_cols,
                        ) = idx_row
                        indexes.append(
                            IndexModel(
                                name=idx_name,
                                columns=list(idx_cols or []),
                                is_unique=bool(is_uniq),
                                is_primary=bool(is_prim),
                                method=idx_method,
                                definition=idx_def,
                            )
                        )

                    tables[tbl_name] = TableModel(
                        name=tbl_name,
                        schema_name=schema_name,
                        columns=columns,
                        constraints=constraints,
                        indexes=indexes,
                    )

        return SchemaModel(tables=tables)


def load_schema_from_ddl(
    ddl_sql: str,
    sandbox_connection_uri: str,
    temp_schema: str = "sqld_temp_schema",
) -> SchemaModel:
    """Execute DDL in an isolated schema and extract SchemaModel.

    Args:
        ddl_sql: User DDL containing CREATE TABLE, ALTER TABLE, etc.
        sandbox_connection_uri: Connection URI to running sandbox container.
        temp_schema: Temporary schema name to isolate execution.

    Returns:
        SchemaModel extracted from the catalogs.
    """
    with psycopg.connect(sandbox_connection_uri) as conn:
        with conn.cursor() as cur:
            # Create isolated namespace and switch search path
            cur.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE;")
            cur.execute(f"CREATE SCHEMA {temp_schema};")
            cur.execute(f"SET search_path TO {temp_schema}, public;")

            # Execute user DDL statements
            cur.execute(ddl_sql)
            conn.commit()

    loader = SchemaLoader(sandbox_connection_uri)
    schema = loader.load_schema(schema_name=temp_schema)

    # Cleanup temporary schema
    with psycopg.connect(sandbox_connection_uri) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE;")
            conn.commit()

    return schema


def parse_ddl_to_schema(ddl_sql: str) -> SchemaModel:
    """Parse DDL SQL statements offline using sqlglot into a typed SchemaModel.

    Args:
        ddl_sql: DDL statements containing CREATE TABLE definitions.

    Returns:
        SchemaModel containing all parsed tables and columns.
    """
    import sqlglot
    from sqlglot import exp

    tables: dict[str, TableModel] = {}
    statements = sqlglot.parse(ddl_sql, read="postgres")

    for stmt in statements:
        if not stmt or not isinstance(stmt, exp.Create):
            continue

        schema_expr = stmt.this
        if not isinstance(schema_expr, exp.Schema):
            continue

        table_name = schema_expr.this.name if schema_expr.this else "unknown"
        columns: dict[str, ColumnModel] = {}
        constraints: list[ConstraintModel] = []

        for col_def in schema_expr.expressions:
            if isinstance(col_def, exp.ColumnDef):
                col_name = col_def.name
                data_type = col_def.kind.sql() if col_def.kind else "text"
                is_nullable = True

                for constraint in col_def.constraints:
                    c_kind = constraint.kind
                    if isinstance(c_kind, exp.NotNullColumnConstraint):
                        is_nullable = False
                    elif isinstance(c_kind, exp.PrimaryKeyColumnConstraint):
                        is_nullable = False
                        constraints.append(
                            ConstraintModel(
                                name=f"pk_{table_name}_{col_name}",
                                type=ConstraintType.PRIMARY_KEY,
                                columns=[col_name],
                            )
                        )
                    elif isinstance(c_kind, exp.UniqueColumnConstraint):
                        constraints.append(
                            ConstraintModel(
                                name=f"uq_{table_name}_{col_name}",
                                type=ConstraintType.UNIQUE,
                                columns=[col_name],
                            )
                        )

                columns[col_name] = ColumnModel(
                    name=col_name,
                    data_type=data_type.lower(),
                    is_nullable=is_nullable,
                )

        tables[table_name] = TableModel(
            name=table_name,
            columns=columns,
            constraints=constraints,
        )

    return SchemaModel(tables=tables)
