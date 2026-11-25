"""
@file test_diagnose.py
@description CLI tests and Phase 3 gate suite for sqld diagnose
@module tests/test_diagnose
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sqldoctor.agent.llm import LLMClient, LLMResponse, LLMToolCall, LLMUsage
from sqldoctor.agent.loop import DiagnosticAgent, DiagnosticResult, VerifiedCandidate
from sqldoctor.cli import app
from sqldoctor.config import AppConfig
from sqldoctor.schema.loader import parse_ddl_to_schema

runner = CliRunner()


def test_cli_diagnose_help() -> None:
    """Verify sqld diagnose --help shows options and description."""
    result = runner.invoke(app, ["diagnose", "--help"])
    assert result.exit_code == 0
    assert "Diagnose a slow PostgreSQL query" in result.output
    assert "--schema" in result.output


def test_cli_diagnose_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify sqld diagnose with --json produces structured JSON."""
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text(
        "CREATE TABLE items (id INT PRIMARY KEY, price NUMERIC NOT NULL);",
        encoding="utf-8",
    )
    query_file = tmp_path / "query.sql"
    query_file.write_text("SELECT id, price FROM items WHERE price > 100;", encoding="utf-8")

    # Patch DiagnosticAgent to return deterministic diagnostic result
    class DummyAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run(self, original_sql: str, schema_sql: str | None = None) -> DiagnosticResult:
            return DiagnosticResult(
                original_sql=original_sql,
                verdict="tested_equivalent",
                best_candidate="SELECT id, price FROM items WHERE price > 100.0",
                proposals_count=1,
                total_cost_usd=0.0002,
                verified_candidates=[
                    VerifiedCandidate(
                        candidate_sql="SELECT id, price FROM items WHERE price > 100.0",
                        verdict="tested_equivalent",
                        mutation_score=1.0,
                    )
                ],
                rejected_candidates=[],
                proposed_indexes=[],
                final_explanation="Precision-normalized filter.",
                audit_trail=[],
            )

    monkeypatch.setattr("sqldoctor.agent.loop.DiagnosticAgent", DummyAgent)

    result = runner.invoke(
        app,
        [
            "diagnose",
            str(query_file),
            "--schema",
            str(schema_file),
            "--json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["verdict"] == "tested_equivalent"
    assert data["best_candidate"] == "SELECT id, price FROM items WHERE price > 100.0"


def test_phase3_gate_ten_queries(tmp_path: Path) -> None:
    """Phase 3 Gate: Run diagnose on 10 slow queries ensuring every candidate receives a verdict.

    Evaluates:
    - 5 equivalent rewrite candidates (subquery unnesting, boolean simplification, union pushdown, etc.)
    - 5 subtle traps where adversary rejects and records counterexample
    """
    schema_ddl = """
    CREATE TABLE customers (
        id INT PRIMARY KEY,
        name TEXT NOT NULL,
        country TEXT NOT NULL,
        is_vip BOOLEAN NOT NULL
    );
    CREATE TABLE orders (
        id INT PRIMARY KEY,
        customer_id INT REFERENCES customers(id),
        amount NUMERIC NOT NULL,
        status TEXT NOT NULL
    );
    """
    schema = parse_ddl_to_schema(schema_ddl)
    config = AppConfig()

    test_queries = [
        # 1. Equivalent: IN subquery vs EXISTS on NOT NULL column
        (
            "SELECT c.id, c.name FROM customers c WHERE c.id IN (SELECT o.customer_id FROM orders o)",
            "SELECT c.id, c.name FROM customers c WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id)",
            True,
        ),
        # 2. Trap: NOT IN vs NOT EXISTS with NULLs
        (
            "SELECT c.id FROM customers c WHERE c.id NOT IN (SELECT o.customer_id FROM orders o WHERE o.customer_id IS NOT NULL)",
            "SELECT c.id FROM customers c WHERE c.id NOT IN (SELECT o.customer_id FROM orders o)",
            False,
        ),
        # 3. Equivalent: Boolean flag comparison
        (
            "SELECT id, name FROM customers WHERE is_vip = TRUE",
            "SELECT id, name FROM customers WHERE is_vip",
            True,
        ),
        # 4. Equivalent: Explicit INNER JOIN
        (
            "SELECT c.name, o.amount FROM customers c, orders o WHERE c.id = o.customer_id AND o.status = 'completed'",
            "SELECT c.name, o.amount FROM customers c INNER JOIN orders o ON c.id = o.customer_id WHERE o.status = 'completed'",
            True,
        ),
        # 5. Trap: Removing DISTINCT
        (
            "SELECT DISTINCT status FROM orders",
            "SELECT status FROM orders",
            False,
        ),
        # 6. Equivalent: BETWEEN range rewrite
        (
            "SELECT id, amount FROM orders WHERE amount >= 10 AND amount <= 50",
            "SELECT id, amount FROM orders WHERE amount BETWEEN 10 AND 50",
            True,
        ),
        # 7. Trap: COUNT(*) vs COUNT(amount) if nullable
        (
            "SELECT count(*) FROM orders",
            "SELECT count(amount) FROM orders",
            True,  # amount is NOT NULL in schema, so equivalent
        ),
        # 8. Trap: Changing UNION to UNION ALL
        (
            "SELECT country FROM customers UNION SELECT status FROM orders",
            "SELECT country FROM customers UNION ALL SELECT status FROM orders",
            False,
        ),
        # 9. Trap: Dropping filter predicate
        (
            "SELECT id, amount FROM orders WHERE amount > 100",
            "SELECT id, amount FROM orders WHERE amount > 50",
            False,
        ),
        # 10. Equivalent: Combining OR with IN
        (
            "SELECT id, status FROM orders WHERE status = 'shipped' OR status = 'delivered'",
            "SELECT id, status FROM orders WHERE status IN ('shipped', 'delivered')",
            True,
        ),
    ]

    for idx, (orig, cand, expected_equiv) in enumerate(test_queries, 1):

        class FixtureLLMClient(LLMClient):
            def __init__(self, candidate_sql: str) -> None:
                super().__init__(cache_dir=tmp_path / "cache")
                self.candidate_sql = candidate_sql

            def generate(
                self,
                messages: Sequence[Any],
                tools: list[dict[str, Any]] | None = None,
                temperature: float = 0.0,
            ) -> LLMResponse:
                return LLMResponse(
                    tool_calls=[
                        LLMToolCall(
                            id=f"call_{idx}",
                            function_name="verify_candidate",
                            arguments={"candidate_sql": self.candidate_sql},
                        ),
                        LLMToolCall(
                            id=f"submit_{idx}",
                            function_name="submit",
                            arguments={
                                "candidate_sql": self.candidate_sql,
                                "explanation": "Proposal",
                            },
                        ),
                    ],
                    usage=LLMUsage(prompt_tokens=80, completion_tokens=30, cost_usd=0.0001),
                )

        agent = DiagnosticAgent(
            config=config,
            schema_model=schema,
            llm_client=FixtureLLMClient(cand),
        )
        res = agent.run(orig)

        # Every candidate must receive an unambiguous verdict
        assert res.verdict in ("tested_equivalent", "no_op", "conditionally_equivalent", "rejected")
        if expected_equiv:
            assert res.verdict in ("tested_equivalent", "no_op", "conditionally_equivalent")
            assert len(res.verified_candidates) >= 1
        else:
            assert res.verdict == "rejected"
            assert len(res.rejected_candidates) >= 1
            assert res.rejected_candidates[0].counterexample is not None
