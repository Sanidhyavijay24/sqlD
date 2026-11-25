"""
@file test_mutator.py
@description Unit tests for ASTMutator and mutation score evaluation
@module tests/test_mutator
"""

from sqldoctor.mutate.engine import ASTMutator


def test_ast_mutator_generates_rules() -> None:
    """Verify ASTMutator generates operators across comparison, constants, boolean."""
    mutator = ASTMutator()
    sql = "SELECT id, count(*) FROM orders WHERE amount > 100 AND status = 'shipped' GROUP BY id;"

    mutants = mutator.generate_mutants(sql)
    assert len(mutants) > 0

    rule_names = {m.rule_name for m in mutants}
    # Must cover comparison flip, constant shift, and boolean swap
    assert "FlipComparison" in rule_names
    assert "ShiftConstant" in rule_names
    assert "SwapBoolean" in rule_names


def test_mutation_adequacy_scoring() -> None:
    """Verify that mutation adequacy scoring computes kill ratio accurately."""
    mutator = ASTMutator()
    sql = "SELECT id FROM items WHERE val > 10;"
    mutants = mutator.generate_mutants(sql)
    assert len(mutants) >= 1

    # Simulate execution where mutant with different predicate produces different output
    def execute_mock(query: str) -> list[tuple[int]]:
        if ">=" in query or "> 101" in query or "> 99" in query:
            return [(1,), (2,)]
        return [(1,)]

    score = mutator.evaluate_adequacy(
        mutants=mutants,
        execute_fn=execute_mock,
        original_output=[(1,)],
    )

    assert score.total_mutants == len(mutants)
    assert score.killed_mutants > 0
    assert 0.0 <= score.score <= 1.0
