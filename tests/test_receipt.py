"""
@file test_receipt.py
@description Unit and CLI tests for standalone SQL receipt generation and replay verification
@module tests/test_receipt
"""

from pathlib import Path

from typer.testing import CliRunner

from sqldoctor.cli import app
from sqldoctor.receipt.replay import ReceiptReplayer
from sqldoctor.receipt.writer import ReceiptWriter
from sqldoctor.schema.loader import parse_ddl_to_schema
from sqldoctor.verifier.adversary_verifier import AdversaryVerifier

runner = CliRunner()


def test_receipt_writer_and_replay_tested_equivalent(tmp_path: Path) -> None:
    """Verify that a generated receipt for equivalent queries replays and confirms TESTED_EQUIVALENT."""
    schema_ddl = "CREATE TABLE users (id INT PRIMARY KEY, active INT NOT NULL);"
    schema = parse_ddl_to_schema(schema_ddl)

    orig = "SELECT id, active FROM users WHERE active = 1 AND active > 0;"
    cand = "SELECT id, active FROM users WHERE active = 1;"

    verifier = AdversaryVerifier(seed=20261123, enumeration_cap=100, fuzz_datasets=10)
    report = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)
    assert report.verdict == "tested_equivalent"

    receipt_file = tmp_path / "receipt_equiv.sql"
    writer = ReceiptWriter(pg_version="17.x")
    writer.write_receipt(
        output_path=receipt_file,
        original_sql=orig,
        candidate_sql=cand,
        verdict_report=report,
        schema=schema,
        explanation="Redundant predicate simplification.",
    )

    assert receipt_file.is_file()
    content = receipt_file.read_text(encoding="utf-8")
    assert "-- Verdict: TESTED_EQUIVALENT" in content
    assert "EXCEPT ALL" in content

    # Replay
    replayer = ReceiptReplayer()
    res = replayer.replay(receipt_file)
    assert res.matches is True
    assert res.observed_verdict == "TESTED_EQUIVALENT"
    assert res.disparity_count == 0


def test_receipt_writer_and_replay_rejected(tmp_path: Path) -> None:
    """Verify that a generated receipt for non-equivalent queries replays and confirms REJECTED with counterexample."""
    schema_ddl = "CREATE TABLE items (id INT PRIMARY KEY, score INT NOT NULL);"
    schema = parse_ddl_to_schema(schema_ddl)

    orig = "SELECT id, score FROM items WHERE score > 50;"
    cand = "SELECT id, score FROM items WHERE score >= 50;"

    verifier = AdversaryVerifier(seed=20261123, enumeration_cap=100, fuzz_datasets=10)
    report = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)
    assert report.verdict == "rejected"
    assert report.counterexample is not None

    receipt_file = tmp_path / "receipt_rejected.sql"
    writer = ReceiptWriter(pg_version="17.x")
    writer.write_receipt(
        output_path=receipt_file,
        original_sql=orig,
        candidate_sql=cand,
        verdict_report=report,
        schema=schema,
        explanation="Off-by-one boundary disparity.",
    )

    content = receipt_file.read_text(encoding="utf-8")
    assert "-- Verdict: REJECTED" in content
    assert "INSERT INTO items" in content

    # Replay
    replayer = ReceiptReplayer()
    res = replayer.replay(receipt_file)
    assert res.matches is True
    assert res.observed_verdict == "REJECTED"
    assert res.disparity_count > 0


def test_cli_replay(tmp_path: Path) -> None:
    """Verify sqld replay CLI command."""
    schema_ddl = "CREATE TABLE tbl (id INT PRIMARY KEY, flag INT NOT NULL);"
    schema = parse_ddl_to_schema(schema_ddl)

    orig = "SELECT id FROM tbl WHERE flag = 1;"
    cand = "SELECT id FROM tbl WHERE flag = 1;"

    verifier = AdversaryVerifier(seed=20261123)
    report = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)

    receipt_file = tmp_path / "test_cli_receipt.sql"
    ReceiptWriter().write_receipt(receipt_file, orig, cand, report, schema)

    result = runner.invoke(app, ["replay", str(receipt_file)])
    assert result.exit_code == 0
    assert "REPLAY VERIFIED" in result.output
