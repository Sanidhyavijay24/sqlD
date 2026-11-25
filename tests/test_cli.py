"""
@file test_cli.py
@description Unit tests for sqld Typer CLI commands
@module tests/test_cli
"""

from typer.testing import CliRunner

from sqldoctor import __version__
from sqldoctor.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    """Verify `sqld --version` displays the current tool version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"sqld version {__version__}" in result.stdout


def test_cli_help() -> None:
    """Verify `sqld --help` lists commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "SQL Doctor" in result.stdout
    assert "up" in result.stdout
    assert "down" in result.stdout
