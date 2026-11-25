"""
@file test_compare.py
@description Unit tests for query result comparison engine
@module tests/test_compare
"""

from sqldoctor.compare.comparator import ResultComparator
from sqldoctor.compare.result import ComparisonVerdict


def test_bag_multiset_order_independence() -> None:
    """Verify that queries without ORDER BY are compared as bags (order independent)."""
    comparator = ResultComparator()
    q_orig = "SELECT id, name FROM users;"
    q_cand = "SELECT id, name FROM users WHERE 1=1;"

    rows_orig = [(1, "alice"), (2, "bob"), (3, "charlie")]
    rows_cand = [(3, "charlie"), (1, "alice"), (2, "bob")]

    res = comparator.compare(q_orig, q_cand, rows_orig, rows_cand)
    assert res.is_equivalent is True
    assert res.verdict == ComparisonVerdict.EQUIVALENT


def test_bag_multiset_duplicate_sensitivity() -> None:
    """Verify that multiset comparison catches duplicate row frequency differences."""
    comparator = ResultComparator()
    q_orig = "SELECT id FROM orders;"
    q_cand = "SELECT DISTINCT id FROM orders;"

    # 1 appears twice in orig, once in cand
    rows_orig = [(1,), (1,), (2,)]
    rows_cand = [(1,), (2,)]

    res = comparator.compare(q_orig, q_cand, rows_orig, rows_cand)
    assert res.is_equivalent is False
    assert res.verdict == ComparisonVerdict.DIFFERENT
    assert res.differences_count > 0


def test_order_by_strict_order_preservation() -> None:
    """Verify that queries with top-level ORDER BY enforce exact row ordering."""
    comparator = ResultComparator()
    q_orig = "SELECT id, score FROM players ORDER BY score DESC;"
    q_cand = "SELECT id, score FROM players ORDER BY id ASC;"

    rows_orig = [(1, 100), (2, 80), (3, 50)]
    rows_cand = [(1, 100), (3, 50), (2, 80)]  # Permuted

    res = comparator.compare(q_orig, q_cand, rows_orig, rows_cand)
    assert res.is_equivalent is False
    assert res.verdict == ComparisonVerdict.DIFFERENT
    assert "Order mismatch" in res.reason


def test_null_is_not_distinct_from_semantics() -> None:
    """Verify that NULL values match using IS NOT DISTINCT FROM semantics."""
    comparator = ResultComparator()
    q_orig = "SELECT id, middle_name FROM employees;"
    q_cand = "SELECT id, middle_name FROM employees;"

    rows_orig = [(1, None), (2, "Lee"), (3, None)]
    rows_cand = [(3, None), (1, None), (2, "Lee")]

    res = comparator.compare(q_orig, q_cand, rows_orig, rows_cand)
    assert res.is_equivalent is True
    assert res.verdict == ComparisonVerdict.EQUIVALENT

    # Disparity check: None vs string
    rows_cand_bad = [(1, "None"), (2, "Lee"), (3, None)]
    res_bad = comparator.compare(q_orig, q_cand, rows_orig, rows_cand_bad)
    assert res_bad.is_equivalent is False


def test_floating_point_tolerance() -> None:
    """Verify that floating point values compare equal within configured tolerance."""
    comparator = ResultComparator(float_rel_tol=1e-5, float_abs_tol=1e-8)
    q_orig = "SELECT avg_score FROM test;"
    q_cand = "SELECT avg_score FROM test;"

    rows_orig = [(10.000001,)]
    rows_cand = [(10.000002,)]

    res = comparator.compare(q_orig, q_cand, rows_orig, rows_cand)
    assert res.is_equivalent is True

    # Beyond tolerance check
    rows_cand_far = [(10.05,)]
    res_far = comparator.compare(q_orig, q_cand, rows_orig, rows_cand_far)
    assert res_far.is_equivalent is False


def test_volatile_functions_return_unverified() -> None:
    """Verify that queries with unpinned volatile functions return unverified."""
    comparator = ResultComparator()
    q_orig = "SELECT id, random() FROM items;"
    q_cand = "SELECT id, 1.0 FROM items;"

    res = comparator.compare(q_orig, q_cand, [(1, 0.42)], [(1, 1.0)])
    assert res.is_equivalent is False
    assert res.verdict == ComparisonVerdict.UNVERIFIED
    assert "volatile function" in res.reason
