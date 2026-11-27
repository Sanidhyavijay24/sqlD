"""
@file tools.py
@description Strict Pydantic-validated MCP tool handlers wrapping SQL Doctor core APIs
@module sqldoctor/mcp/tools
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sqldoctor.agent.loop import DiagnosticAgent
from sqldoctor.config import load_config
from sqldoctor.receipt.replay import ReceiptReplayer
from sqldoctor.receipt.writer import ReceiptWriter
from sqldoctor.report.generator import HTMLReportGenerator
from sqldoctor.schema.loader import parse_ddl_to_schema
from sqldoctor.verifier.adversary_verifier import AdversaryVerdictReport, AdversaryVerifier

MAX_SQL_CHARS = 50_000
MAX_PATH_CHARS = 512


def _validate_safe_path(value: str | None) -> str | None:
    """Reject parent-directory path traversal segments on file path inputs."""
    if value is None:
        return None
    normalized = value.replace("\\", "/")
    if ".." in normalized.split("/"):
        raise ValueError("Path traversal ('..') is not permitted in file paths.")
    return value


def _resolve_sql_or_file(raw_or_path: str) -> str:
    """Resolve raw SQL text or read from a .sql file if a valid local path is given."""
    candidate_path = Path(raw_or_path)
    if "\n" not in raw_or_path and len(raw_or_path) <= MAX_PATH_CHARS and candidate_path.is_file():
        return candidate_path.read_text(encoding="utf-8")
    return raw_or_path


class VerifyRewriteRequest(BaseModel):
    """Input schema for the verify_rewrite MCP tool."""

    model_config = ConfigDict(extra="forbid")

    original_sql: str = Field(
        min_length=1,
        max_length=MAX_SQL_CHARS,
        description="Original PostgreSQL query string or path to .sql file.",
    )
    candidate_sql: str = Field(
        min_length=1,
        max_length=MAX_SQL_CHARS,
        description="Candidate SQL rewrite string or path to .sql file.",
    )
    schema_ddl: str = Field(
        min_length=1,
        max_length=MAX_SQL_CHARS,
        description="PostgreSQL schema DDL string or path to schema .sql file.",
    )
    seed: int | None = Field(
        default=None,
        description="Optional deterministic PRNG seed for adversarial generation.",
    )
    receipt_path: str | None = Field(
        default=None,
        max_length=MAX_PATH_CHARS,
        description="Optional relative path to write standalone receipt.sql.",
    )
    html_path: str | None = Field(
        default=None,
        max_length=MAX_PATH_CHARS,
        description="Optional relative path to write standalone HTML report.",
    )

    @field_validator("receipt_path", "html_path")
    @classmethod
    def check_safe_paths(cls, v: str | None) -> str | None:
        """Validate optional output paths against traversal."""
        return _validate_safe_path(v)


class DiagnoseQueryRequest(BaseModel):
    """Input schema for the diagnose_query MCP tool."""

    model_config = ConfigDict(extra="forbid")

    query_sql: str = Field(
        min_length=1,
        max_length=MAX_SQL_CHARS,
        description="Slow PostgreSQL query string or path to .sql file.",
    )
    schema_ddl: str = Field(
        min_length=1,
        max_length=MAX_SQL_CHARS,
        description="PostgreSQL schema DDL string or path to schema .sql file.",
    )
    config_path: str = Field(
        default="sqld.toml",
        max_length=MAX_PATH_CHARS,
        description="Path to sqld.toml configuration file.",
    )
    receipt_path: str | None = Field(
        default=None,
        max_length=MAX_PATH_CHARS,
        description="Optional path to write standalone receipt.sql for best candidate.",
    )
    html_path: str | None = Field(
        default=None,
        max_length=MAX_PATH_CHARS,
        description="Optional path to write standalone HTML report.",
    )

    @field_validator("config_path", "receipt_path", "html_path")
    @classmethod
    def check_safe_paths(cls, v: str | None) -> str | None:
        """Validate file paths against traversal."""
        return _validate_safe_path(v)


class ReplayReceiptRequest(BaseModel):
    """Input schema for the replay_receipt MCP tool."""

    model_config = ConfigDict(extra="forbid")

    receipt_path: str = Field(
        min_length=1,
        max_length=MAX_PATH_CHARS,
        description="Path to standalone receipt.sql file to replay.",
    )

    @field_validator("receipt_path")
    @classmethod
    def check_safe_path(cls, v: str) -> str:
        """Validate receipt path against traversal."""
        checked = _validate_safe_path(v)
        assert checked is not None
        return checked


def verify_rewrite_tool(
    original_sql: str,
    candidate_sql: str,
    schema_ddl: str,
    seed: int | None = None,
    receipt_path: str | None = None,
    html_path: str | None = None,
) -> dict[str, Any]:
    """Deterministically judge a candidate SQL rewrite against the original query.

    Args:
        original_sql: Original SQL query or path to .sql file.
        candidate_sql: Candidate SQL rewrite or path to .sql file.
        schema_ddl: Schema DDL string or path to schema .sql file.
        seed: Optional deterministic PRNG seed.
        receipt_path: Optional path to write standalone receipt.sql.
        html_path: Optional path to write standalone HTML report.

    Returns:
        Standardized AdversaryVerdictReport serialized as a dict.
    """
    req = VerifyRewriteRequest(
        original_sql=original_sql,
        candidate_sql=candidate_sql,
        schema_ddl=schema_ddl,
        seed=seed,
        receipt_path=receipt_path,
        html_path=html_path,
    )
    orig = _resolve_sql_or_file(req.original_sql)
    cand = _resolve_sql_or_file(req.candidate_sql)
    ddl = _resolve_sql_or_file(req.schema_ddl)

    schema = parse_ddl_to_schema(ddl)
    cfg = load_config("sqld.toml")
    effective_seed = req.seed if req.seed is not None else cfg.adversary.seed

    verifier = AdversaryVerifier(
        seed=effective_seed,
        enumeration_cap=cfg.adversary.enumeration_cap,
        fuzz_datasets=cfg.adversary.fuzz_datasets,
        pg_version=f"{cfg.sandbox.pg_version}.x",
    )
    report = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)

    if req.receipt_path:
        rw = ReceiptWriter(pg_version=f"{cfg.sandbox.pg_version}.x")
        rw.write_receipt(
            output_path=Path(req.receipt_path),
            original_sql=orig,
            candidate_sql=cand,
            verdict_report=report,
            schema=schema,
        )

    if req.html_path:
        gen = HTMLReportGenerator()
        gen.write_report(
            output_path=Path(req.html_path),
            original_sql=orig,
            candidate_sql=cand,
            verdict_report=report,
            pg_version=f"{cfg.sandbox.pg_version}.x",
        )

    return report.model_dump()


def diagnose_query_tool(
    query_sql: str,
    schema_ddl: str,
    config_path: str = "sqld.toml",
    receipt_path: str | None = None,
    html_path: str | None = None,
) -> dict[str, Any]:
    """Diagnose a slow PostgreSQL query with the LLM agent and deterministic adversary.

    Args:
        query_sql: Slow SQL query or path to .sql file.
        schema_ddl: Schema DDL string or path to schema .sql file.
        config_path: Path to sqld.toml configuration.
        receipt_path: Optional path to write standalone receipt.sql.
        html_path: Optional path to write standalone HTML report.

    Returns:
        Standardized DiagnosticResult serialized as a dict.
    """
    req = DiagnoseQueryRequest(
        query_sql=query_sql,
        schema_ddl=schema_ddl,
        config_path=config_path,
        receipt_path=receipt_path,
        html_path=html_path,
    )
    orig = _resolve_sql_or_file(req.query_sql)
    ddl = _resolve_sql_or_file(req.schema_ddl)

    schema = parse_ddl_to_schema(ddl)
    cfg = load_config(req.config_path)

    agent = DiagnosticAgent(config=cfg, schema_model=schema)
    result = agent.run(original_sql=orig)

    if result.best_candidate and (req.receipt_path or req.html_path):
        report_data: dict[str, Any] = (
            result.verified_candidates[0].report
            if result.verified_candidates
            else {
                "verdict": result.verdict,
                "original_sha256": "",
                "candidate_sha256": "",
                "versions": {
                    "tool": "0.1.0",
                    "postgres": f"{cfg.sandbox.pg_version}.x",
                    "model": cfg.agent.model,
                },
                "seed": cfg.adversary.seed,
                "datasets": {"enumerated": 0, "fuzz": 0},
                "mutants": {"score": 1.0, "total": 0, "killed": 0},
            }
        )
        report_obj = AdversaryVerdictReport.model_validate(report_data)

        if req.receipt_path:
            rw = ReceiptWriter(pg_version=f"{cfg.sandbox.pg_version}.x")
            rw.write_receipt(
                output_path=Path(req.receipt_path),
                original_sql=orig,
                candidate_sql=result.best_candidate,
                verdict_report=report_obj,
                schema=schema,
                explanation=result.final_explanation,
            )

        if req.html_path:
            gen = HTMLReportGenerator()
            gen.write_report(
                output_path=Path(req.html_path),
                original_sql=orig,
                candidate_sql=result.best_candidate,
                verdict_report=report_obj,
                pg_version=f"{cfg.sandbox.pg_version}.x",
                proposed_indexes=[idx.model_dump() for idx in result.proposed_indexes],
            )

    return result.model_dump()


def replay_receipt_tool(receipt_path: str) -> dict[str, Any]:
    """Replay a standalone SQL Doctor receipt.sql and verify verdict reproduction.

    Args:
        receipt_path: Path to receipt.sql file.

    Returns:
        ReplayResult serialized as a dict.
    """
    req = ReplayReceiptRequest(receipt_path=receipt_path)
    p = Path(req.receipt_path)
    if not p.is_file():
        raise FileNotFoundError(f"Receipt file not found: {req.receipt_path}")

    replayer = ReceiptReplayer()
    result = replayer.replay(p)
    return result.model_dump()
