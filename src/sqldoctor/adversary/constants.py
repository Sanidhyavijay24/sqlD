"""
@file constants.py
@description Extracts query constants and constructs boundary value pools
@module sqldoctor/adversary/constants
"""

from typing import Any

from sqlglot import exp

from sqldoctor.sql.ast import parse_sql


class ValuePool:
    """Holds targeted scalar boundary values extracted from query ASTs."""

    def __init__(self) -> None:
        """Initialize empty typed value pools."""
        self.integers: set[int] = {0, 1, -1}
        self.floats: set[float] = {0.0, 1.0, -1.0}
        self.strings: set[str] = {"", "a", "b", "test"}
        self.has_null: bool = True

    def get_values_for_type(self, data_type: str) -> list[Any]:
        """Return candidate boundary values matching the PostgreSQL column type.

        Args:
            data_type: PostgreSQL data type string.

        Returns:
            List of representative boundary values.
        """
        d_type = data_type.lower()
        values: list[Any] = []

        if any(t in d_type for t in ("int", "integer", "bigint", "smallint", "serial")):
            values.extend(sorted(self.integers))
        elif any(t in d_type for t in ("numeric", "decimal", "real", "double", "float")):
            values.extend(sorted(self.floats))
        elif any(t in d_type for t in ("char", "varchar", "text")):
            values.extend(sorted(self.strings))
        elif "bool" in d_type:
            values.extend([True, False])
        else:
            values.extend([1, 2, "sample"])

        if self.has_null:
            values.append(None)

        return values


def extract_value_pool(query_sql: str) -> ValuePool:
    """Analyze query AST to extract literals and construct boundary values.

    Args:
        query_sql: SQL query text.

    Returns:
        Populated ValuePool instance.
    """
    ast = parse_sql(query_sql)
    pool = ValuePool()

    for node in ast.walk():
        if isinstance(node, exp.Literal):
            if node.is_int:
                try:
                    c = int(node.this)
                    pool.integers.update({c, c - 1, c + 1})
                except (ValueError, TypeError):
                    pass
            elif node.is_number:
                try:
                    f = float(node.this)
                    pool.floats.update({f, f - 1.0, f + 1.0})
                except (ValueError, TypeError):
                    pass
            elif node.is_string:
                s = str(node.this)
                pool.strings.update({s, s.lower(), s.upper(), f"{s}_dup"})

    return pool
