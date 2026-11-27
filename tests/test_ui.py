"""
@file test_ui.py
@description Unit and CLI tests for the SQL Doctor local Web UI and GitHub Pages showcase
@module tests/test_ui
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from sqldoctor.cli import app
from sqldoctor.ui.server import (
    UIDiagnoseRequest,
    UIVerifyRequest,
    UIWorkloadRequest,
    get_ui_eval_results,
    get_ui_presets,
    handle_verify,
)

runner = CliRunner()


def test_ui_cli_help() -> None:
    """Verify `sqld ui --help` lists host, port, and --no-browser options."""
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    clean_out = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--port" in clean_out
    assert "--no-browser" in clean_out


def test_ui_request_models_strict() -> None:
    """Verify strict extra='forbid' validation on UI API request models."""
    with pytest.raises(ValidationError):
        UIVerifyRequest(
            original_sql="SELECT 1;",
            candidate_sql="SELECT 1;",
            schema_ddl="CREATE TABLE t(id INT);",
            unexpected="nope",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        UIDiagnoseRequest(
            query_sql="SELECT 1;",
            schema_ddl="CREATE TABLE t(id INT);",
            extra=1,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        UIWorkloadRequest(
            stats_export="[]",
            schema_ddl="CREATE TABLE t(id INT);",
            top_n=0,
        )


def test_ui_presets_eval_and_verify_handlers() -> None:
    """Verify presets, eval results loader, and handle_verify equivalent/rejected flows."""
    presets = get_ui_presets()
    assert len(presets["verify_presets"]) >= 3

    ev = get_ui_eval_results()
    assert "trap" in ev and "good" in ev

    demo_ddl = Path("eval/demo_schema.sql").read_text(encoding="utf-8")
    rej = handle_verify(
        UIVerifyRequest(
            original_sql="SELECT id FROM users WHERE age > 21;",
            candidate_sql="SELECT id FROM users WHERE age >= 21;",
            schema_ddl=demo_ddl,
        )
    )
    assert rej["report"]["verdict"] == "rejected"
    assert rej["report"]["counterexample"] is not None
    assert "REJECTED" in rej["receipt_sql"]

    ok = handle_verify(
        UIVerifyRequest(
            original_sql="SELECT id FROM users WHERE age > 18 AND age > 10;",
            candidate_sql="SELECT id FROM users WHERE age > 18;",
            schema_ddl=demo_ddl,
        )
    )
    assert ok["report"]["verdict"] == "tested_equivalent"
    assert "TESTED_EQUIVALENT" in ok["receipt_sql"]


def test_ui_and_pages_html_present() -> None:
    """Verify both local UI index.html and GitHub Pages docs/index.html exist."""
    local_ui = Path("src/sqldoctor/ui/static/index.html")
    gh_pages = Path("docs/index.html")
    assert local_ui.is_file()
    assert gh_pages.is_file()
    assert "SQL DOCTOR" in local_ui.read_text(encoding="utf-8")
    assert "SQL DOCTOR" in gh_pages.read_text(encoding="utf-8")
