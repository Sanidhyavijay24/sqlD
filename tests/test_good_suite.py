"""
@file test_good_suite.py
@description Phase 2 Gate: Verify all 15 good rewrites are accepted
@module tests/test_good_suite
"""

import pytest

from eval.suites.good_suite_v1 import GOOD_CASES_V1, get_good_suite_schema
from sqldoctor.verifier.adversary_verifier import AdversaryVerifier


def test_good_suite_count() -> None:
    """Ensure exactly 15 good rewrite cases exist in v1."""
    assert len(GOOD_CASES_V1) == 15


@pytest.mark.parametrize("good", GOOD_CASES_V1, ids=[g["id"] for g in GOOD_CASES_V1])
def test_adversary_accepts_good_rewrite(good: dict[str, str]) -> None:
    """Verify that known-equivalent rewrites are tested-equivalent or no_op."""
    schema = get_good_suite_schema()
    verifier = AdversaryVerifier(seed=20261123, enumeration_cap=200, fuzz_datasets=5)

    verdict_report = verifier.verify(
        schema=schema,
        original_sql=good["orig"],
        candidate_sql=good["cand"],
    )

    err_msg = (
        f"False reject on {good['id']}: "
        f"expected tested_equivalent or no_op, got {verdict_report.verdict}"
    )
    assert verdict_report.verdict in ("tested_equivalent", "no_op"), err_msg
