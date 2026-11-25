"""
@file test_trap_suite.py
@description Phase 2 Gate: Verify all 25 trap cases are rejected
@module tests/test_trap_suite
"""

import pytest

from eval.suites.trap_suite_v1 import TRAP_CASES_V1, get_trap_suite_schema
from sqldoctor.verifier.adversary_verifier import AdversaryVerifier


def test_trap_suite_count() -> None:
    """Ensure exactly 25 trap cases exist in v1."""
    assert len(TRAP_CASES_V1) == 25


@pytest.mark.parametrize("trap", TRAP_CASES_V1, ids=[t["id"] for t in TRAP_CASES_V1])
def test_adversary_rejects_trap(trap: dict[str, str]) -> None:
    """Verify that every known-wrong rewrite is rejected with a counterexample."""
    schema = get_trap_suite_schema()
    verifier = AdversaryVerifier(seed=20261123, enumeration_cap=500, fuzz_datasets=10)

    verdict_report = verifier.verify(
        schema=schema,
        original_sql=trap["orig"],
        candidate_sql=trap["cand"],
    )

    # Gate requirement: zero false accepts on trap suite
    assert verdict_report.verdict == "rejected", (
        f"False accept on trap {trap['id']} ({trap['category']}): "
        f"expected 'rejected', got '{verdict_report.verdict}'"
    )
    assert verdict_report.counterexample is not None
    assert len(verdict_report.counterexample.dataset) > 0
