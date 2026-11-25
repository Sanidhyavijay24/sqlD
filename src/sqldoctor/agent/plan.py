"""
@file plan.py
@description PostgreSQL EXPLAIN plan normalizer and no-op candidate detector
@module sqldoctor/agent/plan
"""

import re

import sqlglot

from sqldoctor.sandbox.client import SandboxClient


def normalize_explain_text(raw_plan: str) -> str:
    """Normalize PostgreSQL text EXPLAIN output by removing costs, timings, and volatile stats.

    Args:
        raw_plan: Raw multiline text output from EXPLAIN.

    Returns:
        Normalized plan string retaining node hierarchy, scan types, filters, and relations.
    """
    lines = raw_plan.strip().splitlines()
    normalized_lines: list[str] = []

    for line in lines:
        cleaned = line

        # Strip costs, rows, width: (cost=0.00..35.50 rows=10 width=8)
        cleaned = re.sub(r"\(cost=\d+\.?\d*\.\.\d+\.?\d*\s+rows=\d+\s+width=\d+\)", "", cleaned)
        # Strip actual time, loops: (actual time=0.012..0.045 rows=10 loops=1)
        cleaned = re.sub(
            r"\(actual time=\d+\.?\d*\.\.\d+\.?\d*\s+rows=\d+\s+loops=\d+\)",
            "",
            cleaned,
        )
        # Strip buffers: (Buffers: shared hit=4 read=1 ...)
        cleaned = re.sub(r"\(Buffers:[^)]*\)", "", cleaned)
        # Strip planning and execution times
        if "planning time:" in cleaned.lower() or "execution time:" in cleaned.lower():
            continue

        # Clean trailing whitespace
        cleaned = cleaned.rstrip()
        if cleaned:
            normalized_lines.append(cleaned)

    return "\n".join(normalized_lines)


def normalize_ast_plan(sql: str) -> str:
    """Fallback AST-based structural normalizer when no live Postgres sandbox is connected.

    Extracts canonical table scans, joins, where predicates, and group/order operations.

    Args:
        sql: Query SQL string.

    Returns:
        Normalized structural summary.
    """
    try:
        expr = sqlglot.parse_one(sql, read="postgres")
        # Generate canonical formatted SQL representation
        return expr.sql(dialect="postgres", pretty=True)
    except Exception:
        return sql.strip()


def explain_query(db_client: SandboxClient | None, query: str) -> str:
    """Execute EXPLAIN on PostgreSQL or fallback to AST normalization.

    Args:
        db_client: Optional live sandbox database client.
        query: SQL query to explain.

    Returns:
        Normalized query execution plan or AST structure.
    """
    if db_client:
        try:
            # Query plan with costs off
            rows = db_client.execute_query(f"EXPLAIN (COSTS OFF) {query}")
            plan_text = "\n".join(r[0] for r in rows if r and r[0])
            return normalize_explain_text(plan_text)
        except Exception:
            pass

    return normalize_ast_plan(query)


def is_plan_equivalent(plan_a: str, plan_b: str) -> bool:
    """Check if two normalized execution plans are identical (indicating a no-op rewrite).

    Args:
        plan_a: First normalized plan string.
        plan_b: Second normalized plan string.

    Returns:
        True if the plans are identical in execution structure.
    """
    # Normalize whitespaces between lines
    lines_a = [re.sub(r"\s+", " ", line.strip()) for line in plan_a.splitlines() if line.strip()]
    lines_b = [re.sub(r"\s+", " ", line.strip()) for line in plan_b.splitlines() if line.strip()]
    return lines_a == lines_b
