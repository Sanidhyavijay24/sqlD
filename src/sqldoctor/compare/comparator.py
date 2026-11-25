"""
@file comparator.py
@description Deterministic comparison engine for query result sets
@module sqldoctor/compare/comparator
"""

import math
from decimal import Decimal
from typing import Any

from sqlglot import Expression, exp

from sqldoctor.compare.result import ComparisonDetails, ComparisonVerdict
from sqldoctor.sql.ast import parse_sql

# Standard PostgreSQL volatile functions and sqlglot expressions that break determinism
VOLATILE_FUNCTIONS = frozenset(
    {
        "random",
        "now",
        "clock_timestamp",
        "statement_timestamp",
        "transaction_timestamp",
        "timeofday",
        "uuid_generate_v4",
        "gen_random_uuid",
    }
)

VOLATILE_EXPRESSION_TYPES = (
    exp.Rand,
    exp.CurrentTimestamp,
    exp.CurrentDate,
    exp.CurrentTime,
    exp.Uuid,
)


def has_volatile_functions(ast: Expression) -> tuple[bool, str | None]:
    """Check if AST contains volatile functions or expressions that break determinism.

    Args:
        ast: Parsed sqlglot Expression.

    Returns:
        Tuple of (has_volatile, function_name).
    """
    for node in ast.walk():
        if isinstance(node, VOLATILE_EXPRESSION_TYPES):
            return True, node.__class__.__name__.lower()
        if isinstance(node, (exp.Anonymous, exp.Func)):
            fn_name = (node.name or "").lower()
            if fn_name in VOLATILE_FUNCTIONS:
                return True, fn_name
    return False, None


def has_top_level_order_by(ast: Expression) -> bool:
    """Determine whether the root query has a top-level ORDER BY clause.

    Args:
        ast: Parsed sqlglot Expression.

    Returns:
        True if the top-level query explicitly specifies ordering.
    """
    if isinstance(ast, exp.Select):
        return ast.args.get("order") is not None
    # For compound queries (e.g. UNION/EXCEPT), check top-level expression
    return ast.args.get("order") is not None


def value_equals(
    v1: Any,
    v2: Any,
    float_rel_tol: float = 1e-6,
    float_abs_tol: float = 1e-9,
) -> bool:
    """Compare scalar values with IS NOT DISTINCT FROM and float tolerance.

    Args:
        v1: First value.
        v2: Second value.
        float_rel_tol: Relative tolerance for float/decimal comparisons.
        float_abs_tol: Absolute tolerance for float/decimal comparisons.

    Returns:
        True if values are semantically equal.
    """
    # NULL IS NOT DISTINCT FROM NULL -> True
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False

    # Float / Decimal comparison with tolerance
    if isinstance(v1, (float, Decimal)) or isinstance(v2, (float, Decimal)):
        try:
            f1 = float(v1)
            f2 = float(v2)
            if math.isnan(f1) and math.isnan(f2):
                return True
            return math.isclose(f1, f2, rel_tol=float_rel_tol, abs_tol=float_abs_tol)
        except (ValueError, TypeError, OverflowError):
            return bool(v1 == v2)

    return bool(v1 == v2)


def row_equals(
    r1: tuple[Any, ...],
    r2: tuple[Any, ...],
    float_rel_tol: float = 1e-6,
    float_abs_tol: float = 1e-9,
) -> bool:
    """Compare two row tuples element-wise."""
    if len(r1) != len(r2):
        return False
    return all(
        value_equals(v1, v2, float_rel_tol, float_abs_tol) for v1, v2 in zip(r1, r2, strict=True)
    )


class ResultComparator:
    """Compares query results using bag (multiset) or ordered comparison rules."""

    def __init__(
        self,
        float_rel_tol: float = 1e-6,
        float_abs_tol: float = 1e-9,
    ) -> None:
        """Initialize comparator with tolerance parameters.

        Args:
            float_rel_tol: Relative tolerance for floating point numbers.
            float_abs_tol: Absolute tolerance for floating point numbers.
        """
        self.float_rel_tol = float_rel_tol
        self.float_abs_tol = float_abs_tol

    def compare(
        self,
        original_sql: str,
        candidate_sql: str,
        original_rows: list[tuple[Any, ...]],
        candidate_rows: list[tuple[Any, ...]],
    ) -> ComparisonDetails:
        """Compare two execution results according to SQL Doctor equivalence rules.

        Args:
            original_sql: Query text of original query.
            candidate_sql: Query text of candidate rewrite.
            original_rows: Rows returned by executing original query.
            candidate_rows: Rows returned by executing candidate query.

        Returns:
            ComparisonDetails with verdict, disparity count, and sample diff.
        """
        orig_ast = parse_sql(original_sql)
        cand_ast = parse_sql(candidate_sql)

        # 1. Check for volatile functions
        is_orig_volatile, fn_orig = has_volatile_functions(orig_ast)
        is_cand_volatile, fn_cand = has_volatile_functions(cand_ast)

        if is_orig_volatile or is_cand_volatile:
            vol_fn = fn_orig or fn_cand
            return ComparisonDetails(
                is_equivalent=False,
                verdict=ComparisonVerdict.UNVERIFIED,
                reason=f"Query contains unpinned volatile function '{vol_fn}'",
                original_row_count=len(original_rows),
                candidate_row_count=len(candidate_rows),
                differences_count=0,
            )

        orig_len = len(original_rows)
        cand_len = len(candidate_rows)

        # Fast path check on row count
        if orig_len != cand_len:
            sample = {"message": (f"Row count mismatch: orig={orig_len}, cand={cand_len}")}
            return ComparisonDetails(
                is_equivalent=False,
                verdict=ComparisonVerdict.DIFFERENT,
                reason="Row count mismatch",
                original_row_count=orig_len,
                candidate_row_count=cand_len,
                differences_count=abs(orig_len - cand_len),
                sample_diff=sample,
            )

        # 2. Ordered comparison if top-level ORDER BY is declared
        if has_top_level_order_by(orig_ast):
            return self._compare_ordered(original_rows, candidate_rows)

        # 3. Bag (multiset) comparison with EXCEPT ALL semantics
        return self._compare_bags(original_rows, candidate_rows)

    def _compare_ordered(
        self,
        original_rows: list[tuple[Any, ...]],
        candidate_rows: list[tuple[Any, ...]],
    ) -> ComparisonDetails:
        """Compare lists respecting row order."""
        for idx, (r1, r2) in enumerate(zip(original_rows, candidate_rows, strict=True)):
            if not row_equals(r1, r2, self.float_rel_tol, self.float_abs_tol):
                return ComparisonDetails(
                    is_equivalent=False,
                    verdict=ComparisonVerdict.DIFFERENT,
                    reason=f"Order mismatch at row index {idx}",
                    original_row_count=len(original_rows),
                    candidate_row_count=len(candidate_rows),
                    differences_count=1,
                    sample_diff={
                        "row_index": idx,
                        "original_row": list(r1),
                        "candidate_row": list(r2),
                    },
                )

        return ComparisonDetails(
            is_equivalent=True,
            verdict=ComparisonVerdict.EQUIVALENT,
            reason="Results match identically in ordered sequence",
            original_row_count=len(original_rows),
            candidate_row_count=len(candidate_rows),
            differences_count=0,
        )

    def _compare_bags(
        self,
        original_rows: list[tuple[Any, ...]],
        candidate_rows: list[tuple[Any, ...]],
    ) -> ComparisonDetails:
        """Compare results as multisets (bags), matching EXCEPT ALL semantics."""
        # Find unmatched candidate rows using quadratic matching with row_equals
        unmatched_candidate = list(candidate_rows)
        unmatched_original: list[tuple[Any, ...]] = []

        for o_row in original_rows:
            matched_idx = -1
            for idx, c_row in enumerate(unmatched_candidate):
                if row_equals(o_row, c_row, self.float_rel_tol, self.float_abs_tol):
                    matched_idx = idx
                    break

            if matched_idx != -1:
                unmatched_candidate.pop(matched_idx)
            else:
                unmatched_original.append(o_row)

        diff_count = len(unmatched_original) + len(unmatched_candidate)

        if diff_count > 0:
            sample: dict[str, Any] = {}
            if unmatched_original:
                sample["extra_in_original"] = list(unmatched_original[0])
            if unmatched_candidate:
                sample["extra_in_candidate"] = list(unmatched_candidate[0])

            return ComparisonDetails(
                is_equivalent=False,
                verdict=ComparisonVerdict.DIFFERENT,
                reason="Multiset contents differ (EXCEPT ALL disparity)",
                original_row_count=len(original_rows),
                candidate_row_count=len(candidate_rows),
                differences_count=diff_count,
                sample_diff=sample,
            )

        return ComparisonDetails(
            is_equivalent=True,
            verdict=ComparisonVerdict.EQUIVALENT,
            reason="Multisets match exactly across all rows and frequencies",
            original_row_count=len(original_rows),
            candidate_row_count=len(candidate_rows),
            differences_count=0,
        )
