"""
@file test_mcp.py
@description Unit and CLI tests for SQL Doctor MCP server and tool handlers
@module tests/test_mcp
"""

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from sqldoctor.agent.loop import DiagnosticResult, VerifiedCandidate
from sqldoctor.cli import app
from sqldoctor.mcp.tools import (
    DiagnoseQueryRequest,
    ReplayReceiptRequest,
    VerifyRewriteRequest,
    diagnose_query_tool,
    replay_receipt_tool,
    verify_rewrite_tool,
)

runner = CliRunner()

SAMPLE_DDL = """
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL
);
"""


def test_mcp_cli_help() -> None:
    """Verify `sqld mcp --help` lists transport option."""
    result = runner.invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    clean_out = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "MCP server" in clean_out
    assert "--transport" in clean_out


def test_mcp_request_models_strict_and_safe() -> None:
    """Verify strict Pydantic validation and path traversal protection."""
    with pytest.raises(ValidationError):
        VerifyRewriteRequest(
            original_sql="SELECT 1;",
            candidate_sql="SELECT 1;",
            schema_ddl=SAMPLE_DDL,
            extra_field="nope",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        VerifyRewriteRequest(
            original_sql="SELECT 1;",
            candidate_sql="SELECT 1;",
            schema_ddl=SAMPLE_DDL,
            receipt_path="../outside.sql",
        )

    with pytest.raises(ValidationError):
        DiagnoseQueryRequest(
            query_sql="SELECT 1;",
            schema_ddl=SAMPLE_DDL,
            html_path="../../secret.html",
        )

    with pytest.raises(ValidationError):
        ReplayReceiptRequest(receipt_path="../evil.sql")


def test_verify_rewrite_tool_equivalent_and_rejected(tmp_path: Path) -> None:
    """Verify verify_rewrite_tool judges equivalent and buggy rewrites and emits receipts."""
    receipt_file = tmp_path / "mcp_receipt.sql"
    html_file = tmp_path / "mcp_report.html"

    ok_res = verify_rewrite_tool(
        original_sql="SELECT id FROM users WHERE age > 18 AND age > 10;",
        candidate_sql="SELECT id FROM users WHERE age > 18;",
        schema_ddl=SAMPLE_DDL,
        receipt_path=str(receipt_file),
        html_path=str(html_file),
    )
    assert ok_res["verdict"] == "tested_equivalent"
    assert receipt_file.is_file()
    assert html_file.is_file()

    replay_res = replay_receipt_tool(str(receipt_file))
    assert replay_res["matches"] is True
    assert replay_res["observed_verdict"] == "TESTED_EQUIVALENT"

    bad_res = verify_rewrite_tool(
        original_sql="SELECT id FROM users WHERE age > 21;",
        candidate_sql="SELECT id FROM users WHERE age >= 21;",
        schema_ddl=SAMPLE_DDL,
    )
    assert bad_res["verdict"] == "rejected"
    assert bad_res["counterexample"] is not None


def test_diagnose_query_tool_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify diagnose_query_tool returns structured DiagnosticResult and writes receipt."""

    class DummyAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run(self, original_sql: str) -> DiagnosticResult:
            cand = VerifiedCandidate(
                candidate_sql="SELECT id, name FROM users WHERE age > 18;",
                verdict="tested_equivalent",
                mutation_score=1.0,
                report={
                    "schema_version": 1,
                    "verdict": "tested_equivalent",
                    "original_sha256": "abc",
                    "candidate_sha256": "def",
                    "versions": {"tool": "0.1.0", "postgres": "17.x", "model": "mock"},
                    "seed": 20261123,
                    "datasets": {"enumerated": 10, "targeted": 0, "fuzz": 5},
                    "mutants": {"total": 2, "killed": 2, "score": 1.0},
                },
            )
            return DiagnosticResult(
                original_sql=original_sql,
                verdict="tested_equivalent",
                best_candidate=cand.candidate_sql,
                verified_candidates=[cand],
                total_cost_usd=0.0,
            )

    monkeypatch.setattr("sqldoctor.mcp.tools.DiagnosticAgent", DummyAgent)

    receipt_file = tmp_path / "diag_receipt.sql"
    res = diagnose_query_tool(
        query_sql="SELECT id, name FROM users WHERE age > 18 AND age > 10;",
        schema_ddl=SAMPLE_DDL,
        receipt_path=str(receipt_file),
    )
    assert res["verdict"] == "tested_equivalent"
    assert res["best_candidate"] == "SELECT id, name FROM users WHERE age > 18;"
    assert receipt_file.is_file()
