"""
@file ast.py
@description SQL parsing, normalization, and round-trip verification using sqlglot
@module sqldoctor/sql/ast
"""

from sqlglot import Expression, parse_one, transpile
from sqlglot.diff import Keep, diff


class SQLAstError(Exception):
    """Raised when SQL parsing or AST normalization fails."""


def parse_sql(sql: str) -> Expression:
    """Parse a PostgreSQL query string into an AST Expression.

    Args:
        sql: Input SQL query string.

    Returns:
        sqlglot Expression representing the AST.

    Raises:
        SQLAstError: If the SQL string cannot be parsed as PostgreSQL syntax.
    """
    try:
        return parse_one(sql, read="postgres")
    except Exception as exc:
        raise SQLAstError(f"Failed to parse SQL with postgres dialect: {exc}") from exc


def normalize_sql(sql: str) -> str:
    """Normalize and format a SQL query into canonical PostgreSQL syntax.

    Args:
        sql: Input SQL query string.

    Returns:
        Canonical formatted SQL string.

    Raises:
        SQLAstError: If parsing or transpile fails.
    """
    try:
        results = transpile(sql, read="postgres", write="postgres", pretty=True)
        if not results:
            raise SQLAstError("Empty output from transpile")
        return results[0]
    except Exception as exc:
        raise SQLAstError(f"Normalization failed: {exc}") from exc


def round_trip(sql: str) -> tuple[bool, str, str]:
    """Test AST round-tripping for a SQL query.

    Parses SQL, generates canonical SQL, parses that canonical SQL again,
    and compares ASTs for semantic identity.

    Args:
        sql: Original SQL query string.

    Returns:
        Tuple of (is_equivalent, original_normalized, roundtrip_normalized).
    """
    first_pass_ast = parse_sql(sql)
    first_pass_sql = first_pass_ast.sql(dialect="postgres", pretty=True)

    second_pass_ast = parse_sql(first_pass_sql)
    second_pass_sql = second_pass_ast.sql(dialect="postgres", pretty=True)

    # Fast equivalence check via canonical representation or direct AST equality
    if first_pass_sql == second_pass_sql or first_pass_ast == second_pass_ast:
        return True, first_pass_sql, second_pass_sql

    # Check structural AST diff excluding Keep operations
    ast_differences = [e for e in diff(first_pass_ast, second_pass_ast) if not isinstance(e, Keep)]
    is_equivalent = len(ast_differences) == 0

    return is_equivalent, first_pass_sql, second_pass_sql
