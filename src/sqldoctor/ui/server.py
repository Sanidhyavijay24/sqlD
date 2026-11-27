"""
@file server.py
@description FastAPI local web server powering the SQL Doctor Teletype + Dither UI
@module sqldoctor/ui/server
"""

import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sqldoctor import __version__
from sqldoctor.agent.loop import DiagnosticAgent
from sqldoctor.config import load_config
from sqldoctor.receipt.writer import ReceiptWriter
from sqldoctor.sandbox.client import SandboxClient
from sqldoctor.schema.loader import parse_ddl_to_schema
from sqldoctor.verifier.adversary_verifier import AdversaryVerdictReport, AdversaryVerifier
from sqldoctor.workload.analyzer import WorkloadAnalyzer

MAX_SQL_LEN = 50_000
STATIC_DIR = Path(__file__).parent / "static"


class UIVerifyRequest(BaseModel):
    """Strict input schema for POST /api/verify."""

    model_config = ConfigDict(extra="forbid")

    original_sql: str = Field(min_length=1, max_length=MAX_SQL_LEN)
    candidate_sql: str = Field(min_length=1, max_length=MAX_SQL_LEN)
    schema_ddl: str = Field(min_length=1, max_length=MAX_SQL_LEN)
    seed: int | None = None


class UIDiagnoseRequest(BaseModel):
    """Strict input schema for POST /api/diagnose."""

    model_config = ConfigDict(extra="forbid")

    query_sql: str = Field(min_length=1, max_length=MAX_SQL_LEN)
    schema_ddl: str = Field(min_length=1, max_length=MAX_SQL_LEN)


class UIWorkloadRequest(BaseModel):
    """Strict input schema for POST /api/workload."""

    model_config = ConfigDict(extra="forbid")

    stats_export: str = Field(min_length=1, max_length=200_000)
    schema_ddl: str = Field(min_length=1, max_length=MAX_SQL_LEN)
    top_n: int = Field(default=3, ge=1, le=20)
    budget_usd: float = Field(default=0.50, ge=0.0, le=10.0)


def _check_sandbox_online(config_path: Path | str = "sqld.toml") -> bool:
    """Check whether the Docker PostgreSQL 17 sandbox is currently reachable."""
    cfg = load_config(config_path)
    try:
        client = SandboxClient(cfg.sandbox)
        client.execute_query("SELECT 1;")
        return True
    except Exception:
        return False


def get_ui_health() -> dict[str, Any]:
    """Return runtime status for the UI header."""
    cfg = load_config("sqld.toml")
    return {
        "version": __version__,
        "pg_version": f"{cfg.sandbox.pg_version}.x",
        "pg_sandbox_online": _check_sandbox_online(),
        "gemini_configured": bool(cfg.agent.api_key),
        "model": cfg.agent.model,
    }


def get_ui_presets() -> dict[str, Any]:
    """Return built-in interactive SQL presets and example files."""
    demo_schema = (
        Path("eval/demo_schema.sql").read_text(encoding="utf-8")
        if Path("eval/demo_schema.sql").is_file()
        else "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100), age INT);"
    )
    ex_schema = (
        Path("examples/schema.sql").read_text(encoding="utf-8")
        if Path("examples/schema.sql").is_file()
        else demo_schema
    )
    ex_query = (
        Path("examples/slow_query.sql").read_text(encoding="utf-8")
        if Path("examples/slow_query.sql").is_file()
        else "SELECT id FROM users WHERE age > 18;"
    )
    ex_stats = (
        Path("examples/pg_stat_statements.json").read_text(encoding="utf-8")
        if Path("examples/pg_stat_statements.json").is_file()
        else "[]"
    )

    return {
        "verify_presets": [
            {
                "id": "boundary_trap",
                "label": "Trap: age > 21 vs age >= 21",
                "schema_ddl": demo_schema,
                "original_sql": "SELECT id FROM users WHERE age > 21;",
                "candidate_sql": "SELECT id FROM users WHERE age >= 21;",
            },
            {
                "id": "redundant_pred",
                "label": "Pass: Redundant age > 10",
                "schema_ddl": demo_schema,
                "original_sql": "SELECT id FROM users WHERE age > 18 AND age > 10;",
                "candidate_sql": "SELECT id FROM users WHERE age > 18;",
            },
            {
                "id": "comma_to_join",
                "label": "Pass: Comma Join -> INNER JOIN",
                "schema_ddl": ex_schema,
                "original_sql": ex_query,
                "candidate_sql": (
                    "SELECT c.id, c.name, o.amount\n"
                    "FROM customers c\n"
                    "INNER JOIN orders o ON c.id = o.customer_id\n"
                    "WHERE o.status = 'completed';"
                ),
            },
        ],
        "diagnose_preset": {
            "schema_ddl": ex_schema,
            "query_sql": ex_query,
        },
        "workload_preset": {
            "schema_ddl": ex_schema,
            "stats_export": ex_stats,
        },
    }


def get_ui_eval_results() -> dict[str, Any]:
    """Load persisted Trap, Good, and Perf evaluation results."""
    out: dict[str, Any] = {"trap": {}, "good": {}, "perf": []}
    trap_p = Path("eval/results/trap_results.json")
    good_p = Path("eval/results/good_results.json")
    perf_p = Path("eval/results/perf_results.json")

    if trap_p.is_file():
        out["trap"] = json.loads(trap_p.read_text(encoding="utf-8"))
    if good_p.is_file():
        out["good"] = json.loads(good_p.read_text(encoding="utf-8"))
    if perf_p.is_file():
        out["perf"] = json.loads(perf_p.read_text(encoding="utf-8"))
    return out


def handle_verify(req: UIVerifyRequest) -> dict[str, Any]:
    """Execute AdversaryVerifier and emit verdict JSON + standalone receipt_sql."""
    cfg = load_config("sqld.toml")
    schema = parse_ddl_to_schema(req.schema_ddl)
    seed = req.seed if req.seed is not None else cfg.adversary.seed

    verifier = AdversaryVerifier(
        seed=seed,
        enumeration_cap=cfg.adversary.enumeration_cap,
        fuzz_datasets=cfg.adversary.fuzz_datasets,
        pg_version=f"{cfg.sandbox.pg_version}.x",
    )
    report = verifier.verify(
        schema=schema,
        original_sql=req.original_sql,
        candidate_sql=req.candidate_sql,
    )

    rw = ReceiptWriter(pg_version=f"{cfg.sandbox.pg_version}.x")
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        rw.write_receipt(
            output_path=tmp_path,
            original_sql=req.original_sql,
            candidate_sql=req.candidate_sql,
            verdict_report=report,
            schema=schema,
        )
        receipt_sql = tmp_path.read_text(encoding="utf-8")
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "report": report.model_dump(),
        "receipt_sql": receipt_sql,
    }


def handle_diagnose(req: UIDiagnoseRequest) -> dict[str, Any]:
    """Execute DiagnosticAgent and return diagnosis + receipt_sql."""
    cfg = load_config("sqld.toml")
    schema = parse_ddl_to_schema(req.schema_ddl)
    agent = DiagnosticAgent(config=cfg, schema_model=schema)
    result = agent.run(original_sql=req.query_sql)

    receipt_sql = ""
    if result.best_candidate:
        rep_data: dict[str, Any] = (
            result.verified_candidates[0].report
            if result.verified_candidates
            else {
                "verdict": result.verdict,
                "original_sha256": "",
                "candidate_sha256": "",
                "versions": {
                    "tool": __version__,
                    "postgres": f"{cfg.sandbox.pg_version}.x",
                    "model": cfg.agent.model,
                },
                "seed": cfg.adversary.seed,
                "datasets": {"enumerated": 0, "fuzz": 0},
                "mutants": {"score": 1.0, "total": 0, "killed": 0},
            }
        )
        rep_obj = AdversaryVerdictReport.model_validate(rep_data)
        rw = ReceiptWriter(pg_version=f"{cfg.sandbox.pg_version}.x")
        with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            rw.write_receipt(
                output_path=tmp_path,
                original_sql=req.query_sql,
                candidate_sql=result.best_candidate,
                verdict_report=rep_obj,
                schema=schema,
                explanation=result.final_explanation,
            )
            receipt_sql = tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)

    return {
        "result": result.model_dump(),
        "receipt_sql": receipt_sql,
    }


def handle_workload(req: UIWorkloadRequest) -> dict[str, Any]:
    """Execute WorkloadAnalyzer (live HypoPG if Docker sandbox is up, else offline)."""
    cfg = load_config("sqld.toml")
    schema = parse_ddl_to_schema(req.schema_ddl)
    db_client: SandboxClient | None = None
    try:
        cand_client = SandboxClient(cfg.sandbox)
        cand_client.execute_query("SELECT 1;")
        db_client = cand_client
    except Exception:
        db_client = None

    analyzer = WorkloadAnalyzer(config=cfg, schema=schema, db_client=db_client)
    report = analyzer.analyze(
        stats_source=req.stats_export,
        top_n=req.top_n,
        budget_usd=req.budget_usd,
    )
    return report.model_dump()


def create_ui_app() -> Any:
    """Create and configure the FastAPI application for SQL Doctor UI."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI and Uvicorn are required for `sqld ui`. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    app = FastAPI(title="SQL Doctor Lab UI", version=__version__)

    def serve_index() -> HTMLResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.is_file():
            raise HTTPException(status_code=404, detail="UI static index.html not found.")
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    def api_verify(req: UIVerifyRequest) -> dict[str, Any]:
        try:
            return handle_verify(req)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def api_diagnose(req: UIDiagnoseRequest) -> dict[str, Any]:
        try:
            return handle_diagnose(req)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def api_workload(req: UIWorkloadRequest) -> dict[str, Any]:
        try:
            return handle_workload(req)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    app.add_api_route("/", serve_index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/api/health", get_ui_health, methods=["GET"])
    app.add_api_route("/api/presets", get_ui_presets, methods=["GET"])
    app.add_api_route("/api/eval", get_ui_eval_results, methods=["GET"])
    app.add_api_route("/api/verify", api_verify, methods=["POST"])
    app.add_api_route("/api/diagnose", api_diagnose, methods=["POST"])
    app.add_api_route("/api/workload", api_workload, methods=["POST"])

    return app


def run_ui_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    """Launch the local SQL Doctor UI with Uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Uvicorn is required for `sqld ui`. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    app = create_ui_app()
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(app, host=host, port=port)
