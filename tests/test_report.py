"""
@file test_report.py
@description Unit tests for static HTML report generation and end-to-end receipt/report flags
@module tests/test_report
"""

from pathlib import Path

from typer.testing import CliRunner

from sqldoctor.bench.models import BenchmarkReport, ScaleMetrics
from sqldoctor.cli import app
from sqldoctor.report.generator import HTMLReportGenerator
from sqldoctor.schema.loader import parse_ddl_to_schema
from sqldoctor.verifier.adversary_verifier import AdversaryVerifier

runner = CliRunner()


def test_html_report_rendering() -> None:
    """Verify HTML report generator creates valid HTML with all required sections."""
    schema_ddl = "CREATE TABLE users (id INT PRIMARY KEY, email TEXT NOT NULL);"
    schema = parse_ddl_to_schema(schema_ddl)
    orig = "SELECT id FROM users WHERE email = 'a@b.com' AND 1=1;"
    cand = "SELECT id FROM users WHERE email = 'a@b.com';"

    verifier = AdversaryVerifier(seed=20261123, enumeration_cap=50, fuzz_datasets=5)
    report = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)

    bench = BenchmarkReport(
        original_sql=orig,
        candidate_sql=cand,
        scales=[
            ScaleMetrics(
                scale=1000,
                repeats=5,
                original_buffers_p50=120.0,
                original_buffers_min=110,
                original_buffers_max=130,
                candidate_buffers_p50=30.0,
                candidate_buffers_min=25,
                candidate_buffers_max=35,
                buffer_speedup_ratio=4.0,
                original_time_ms_p50=4.5,
                candidate_time_ms_p50=1.1,
                time_speedup_ratio=4.09,
            )
        ],
        overall_buffer_speedup=4.0,
        overall_time_speedup=4.09,
        summary="Observed 4.0x buffer speedup.",
    )

    generator = HTMLReportGenerator()
    html = generator.render(
        original_sql=orig,
        candidate_sql=cand,
        verdict_report=report,
        benchmark_report=bench,
        proposed_indexes=["CREATE INDEX idx_users_email ON users(email);"],
        explanation="Index scan optimization over email.",
    )

    assert "<!DOCTYPE html>" in html
    assert "TESTED_EQUIVALENT" in html
    assert "idx_users_email" in html
    assert "4.0x" in html
    assert "a@b.com" in html


def test_verify_with_receipt_and_html_cli(tmp_path: Path) -> None:
    """Verify sqld verify --receipt ... --html ... creates both files."""
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE t (id INT PRIMARY KEY, v INT);", encoding="utf-8")
    receipt_file = tmp_path / "receipt.sql"
    html_file = tmp_path / "report.html"

    result = runner.invoke(
        app,
        [
            "verify",
            "SELECT id FROM t WHERE v > 10 AND v > 5;",
            "SELECT id FROM t WHERE v > 10;",
            "--schema",
            str(schema_file),
            "--receipt",
            str(receipt_file),
            "--html",
            str(html_file),
        ],
    )
    assert result.exit_code == 0
    assert receipt_file.is_file()
    assert html_file.is_file()
    assert "TESTED_EQUIVALENT" in receipt_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_file.read_text(encoding="utf-8")
