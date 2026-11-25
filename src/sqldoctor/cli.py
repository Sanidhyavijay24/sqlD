"""
@file cli.py
@description Command-line interface for SQL Doctor (sqld)
@module sqldoctor/cli
"""

from pathlib import Path

import typer

from sqldoctor import __version__
from sqldoctor.config import load_config
from sqldoctor.sandbox.manager import SandboxManager, SandboxManagerError

app = typer.Typer(
    name="sqld",
    help="SQL Doctor: Agentic PostgreSQL query optimizer.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show SQL Doctor version and exit."
    ),
) -> None:
    """Root entry point displaying tool version if requested."""
    if version:
        typer.echo(f"sqld version {__version__}")
        raise typer.Exit(code=0)


@app.command("up")
def sandbox_up(
    config_path: Path = typer.Option(
        Path("sqld.toml"), "--config", "-c", help="Path to sqld.toml configuration."
    ),
    port: int | None = typer.Option(None, "--port", "-p", help="Override host port for sandbox."),
    timeout: int = typer.Option(45, "--timeout", help="Readiness timeout in seconds."),
) -> None:
    """Start the PostgreSQL sandbox container and await readiness."""
    cfg = load_config(config_path)
    if port is not None:
        # Override port dynamically
        cfg = cfg.model_copy(update={"sandbox": cfg.sandbox.model_copy(update={"port": port})})

    manager = SandboxManager(cfg.sandbox)
    typer.echo(
        f"Starting PostgreSQL {cfg.sandbox.pg_version} sandbox on port {cfg.sandbox.port}..."
    )

    try:
        manager.start(wait=True, timeout_sec=timeout)
        typer.echo(f"[+] Sandbox is ready: {manager.connection_uri}")
    except SandboxManagerError as exc:
        typer.secho(f"[-] Failed to start sandbox: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc


@app.command("down")
def sandbox_down(
    config_path: Path = typer.Option(
        Path("sqld.toml"), "--config", "-c", help="Path to sqld.toml configuration."
    ),
) -> None:
    """Stop and remove the running PostgreSQL sandbox container."""
    cfg = load_config(config_path)
    manager = SandboxManager(cfg.sandbox)

    typer.echo("Stopping PostgreSQL sandbox container...")
    try:
        manager.stop()
        typer.echo("[+] Sandbox stopped and removed.")
    except SandboxManagerError as exc:
        typer.secho(f"[-] Error stopping sandbox: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=3) from exc


@app.command("verify")
def verify_rewrite(
    original: str = typer.Argument(..., help="Original SQL query string or path to .sql file."),
    candidate: str = typer.Argument(..., help="Candidate SQL rewrite string or path to .sql file."),
    schema_path: Path = typer.Option(..., "--schema", "-s", help="Path to schema DDL .sql file."),
    config_path: Path = typer.Option(
        Path("sqld.toml"), "--config", "-c", help="Path to sqld.toml configuration."
    ),
    seed: int | None = typer.Option(
        None, "--seed", help="Deterministic seed for adversarial generation."
    ),
    receipt_path: Path | None = typer.Option(
        None, "--receipt", "-r", help="Path to write standalone receipt.sql."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", help="Path to write standalone HTML report."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw standardized verdict JSON."),
) -> None:
    """Judge a candidate rewrite deterministically against the original query."""
    import json

    from sqldoctor.receipt.writer import ReceiptWriter
    from sqldoctor.report.generator import HTMLReportGenerator
    from sqldoctor.schema.loader import parse_ddl_to_schema
    from sqldoctor.verifier.adversary_verifier import AdversaryVerifier

    # Resolve original and candidate (read file if path exists)
    orig_sql = original
    cand_sql = candidate
    orig_p = Path(original)
    cand_p = Path(candidate)

    if orig_p.is_file():
        orig_sql = orig_p.read_text(encoding="utf-8")
    if cand_p.is_file():
        cand_sql = cand_p.read_text(encoding="utf-8")

    if not schema_path.is_file():
        typer.secho(f"[-] Schema file not found: {schema_path}", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    ddl_sql = schema_path.read_text(encoding="utf-8")
    schema = parse_ddl_to_schema(ddl_sql)

    cfg = load_config(config_path)
    effective_seed = seed if seed is not None else cfg.adversary.seed

    verifier = AdversaryVerifier(
        seed=effective_seed,
        enumeration_cap=cfg.adversary.enumeration_cap,
        fuzz_datasets=cfg.adversary.fuzz_datasets,
        pg_version=f"{cfg.sandbox.pg_version}.x",
    )

    verdict_report = verifier.verify(
        schema=schema,
        original_sql=orig_sql,
        candidate_sql=cand_sql,
    )

    # Write receipt if requested
    if receipt_path:
        rw = ReceiptWriter(pg_version=f"{cfg.sandbox.pg_version}.x")
        rw.write_receipt(
            output_path=receipt_path,
            original_sql=orig_sql,
            candidate_sql=cand_sql,
            verdict_report=verdict_report,
            schema=schema,
        )
        if not json_output:
            typer.secho(f"[+] Receipt written to: {receipt_path}", fg=typer.colors.CYAN)

    # Write HTML report if requested
    if html_path:
        gen = HTMLReportGenerator()
        gen.write_report(
            output_path=html_path,
            original_sql=orig_sql,
            candidate_sql=cand_sql,
            verdict_report=verdict_report,
            pg_version=f"{cfg.sandbox.pg_version}.x",
        )
        if not json_output:
            typer.secho(f"[+] HTML report written to: {html_path}", fg=typer.colors.CYAN)

    if json_output:
        typer.echo(json.dumps(verdict_report.model_dump(), indent=2))
    else:
        typer.echo(f"Verdict: {verdict_report.verdict.upper()}")
        typer.echo(f"Seed: {verdict_report.seed}")
        typer.echo(
            f"Datasets evaluated: {sum(verdict_report.datasets.values())} "
            f"(enumerated={verdict_report.datasets['enumerated']}, "
            f"fuzz={verdict_report.datasets['fuzz']})"
        )

        if verdict_report.verdict == "rejected":
            typer.secho("[-] Candidate REJECTED. Counterexample found:", fg=typer.colors.RED)
            if verdict_report.counterexample:
                typer.echo(f"Reason: {verdict_report.counterexample.reason}")
                typer.echo(f"Minimal Data: {verdict_report.counterexample.dataset}")
                typer.echo(f"Original output: {verdict_report.counterexample.original_output}")
                typer.echo(f"Candidate output: {verdict_report.counterexample.candidate_output}")
        elif verdict_report.verdict == "tested_equivalent":
            typer.secho(
                f"[+] Candidate TESTED EQUIVALENT. "
                f"Mutation score: {verdict_report.mutants.get('score', 1.0) * 100:.1f}%",
                fg=typer.colors.GREEN,
            )

    # Standardized exit codes
    if verdict_report.verdict in (
        "tested_equivalent",
        "no_op",
        "conditionally_equivalent",
    ):
        raise typer.Exit(code=0)
    elif verdict_report.verdict == "rejected":
        raise typer.Exit(code=1)
    elif verdict_report.verdict == "unverified":
        raise typer.Exit(code=2)
    else:
        raise typer.Exit(code=3)


@app.command("diagnose")
def diagnose_query(
    query: str = typer.Argument(..., help="Path to SQL query file or raw SQL query string."),
    schema_path: Path = typer.Option(..., "--schema", "-s", help="Path to schema DDL .sql file."),
    config_path: Path = typer.Option(
        Path("sqld.toml"), "--config", "-c", help="Path to sqld.toml configuration."
    ),
    receipt_path: Path | None = typer.Option(
        None, "--receipt", "-r", help="Path to write standalone receipt.sql for best candidate."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", help="Path to write standalone HTML report."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw standardized diagnosis JSON."
    ),
) -> None:
    """Diagnose a slow PostgreSQL query using the agent loop and deterministic adversary."""
    import json

    from sqldoctor.agent.loop import DiagnosticAgent
    from sqldoctor.receipt.writer import ReceiptWriter
    from sqldoctor.report.generator import HTMLReportGenerator
    from sqldoctor.schema.loader import parse_ddl_to_schema
    from sqldoctor.verifier.adversary_verifier import AdversaryVerdictReport

    orig_sql = query
    query_p = Path(query)
    if query_p.is_file():
        orig_sql = query_p.read_text(encoding="utf-8")

    if not schema_path.is_file():
        typer.secho(f"[-] Schema file not found: {schema_path}", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    ddl_sql = schema_path.read_text(encoding="utf-8")
    schema = parse_ddl_to_schema(ddl_sql)
    cfg = load_config(config_path)

    agent = DiagnosticAgent(config=cfg, schema_model=schema)
    result = agent.run(original_sql=orig_sql)

    # Save receipt if requested and best candidate exists
    if receipt_path and result.best_candidate:
        rw = ReceiptWriter(pg_version=f"{cfg.sandbox.pg_version}.x")
        # Build verdict report from verified candidate or default
        report_data = (
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
        verdict_rep = AdversaryVerdictReport.model_validate(report_data)
        rw.write_receipt(
            output_path=receipt_path,
            original_sql=orig_sql,
            candidate_sql=result.best_candidate,
            verdict_report=verdict_rep,
            schema=schema,
            explanation=result.final_explanation,
        )
        if not json_output:
            typer.secho(f"[+] Receipt written to: {receipt_path}", fg=typer.colors.CYAN)

    # Save HTML report if requested
    if html_path:
        gen = HTMLReportGenerator()
        rep_dict = (
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
        verdict_rep = AdversaryVerdictReport.model_validate(rep_dict)
        gen.write_report(
            output_path=html_path,
            original_sql=orig_sql,
            candidate_sql=result.best_candidate or orig_sql,
            verdict_report=verdict_rep,
            proposed_indexes=result.proposed_indexes,
            explanation=result.final_explanation,
            pg_version=f"{cfg.sandbox.pg_version}.x",
        )
        if not json_output:
            typer.secho(f"[+] HTML report written to: {html_path}", fg=typer.colors.CYAN)

    if json_output:
        typer.echo(json.dumps(result.model_dump(), indent=2))
    else:
        typer.echo("=" * 60)
        typer.echo("SQL DOCTOR DIAGNOSTIC REPORT")
        typer.echo("=" * 60)
        typer.echo(f"Proposals evaluated: {result.proposals_count}")
        typer.echo(f"Total LLM Cost: ${result.total_cost_usd:.4f}")
        typer.echo(f"Verdict: {result.verdict.upper()}")

        if result.best_candidate:
            typer.secho("\n[+] Recommended Rewrite:", fg=typer.colors.GREEN, bold=True)
            typer.echo(result.best_candidate)

        if result.proposed_indexes:
            typer.secho("\n[*] Proposed Indexes:", fg=typer.colors.CYAN, bold=True)
            for p_idx in result.proposed_indexes:
                typer.echo(f"  - {p_idx.index_sql}")
                if p_idx.explanation:
                    typer.echo(f"    Rationale: {p_idx.explanation}")

        if result.rejected_candidates:
            typer.secho(
                f"\n[-] Rejected Candidates ({len(result.rejected_candidates)}):",
                fg=typer.colors.YELLOW,
            )
            for rej_i, rej in enumerate(result.rejected_candidates, 1):
                typer.echo(f"  Candidate #{rej_i} Reason: {rej.disparity_reason}")

        if result.final_explanation:
            typer.echo(f"\nNotes: {result.final_explanation}")

    # Standardized exit codes
    if result.verdict in ("tested_equivalent", "conditionally_equivalent", "no_op"):
        raise typer.Exit(code=0)
    elif result.verdict == "rejected":
        raise typer.Exit(code=1)
    elif result.verdict == "unverified":
        raise typer.Exit(code=2)
    else:
        raise typer.Exit(code=3)


@app.command("bench")
def benchmark_pair(
    original: str = typer.Argument(..., help="Original SQL query string or path to .sql file."),
    candidate: str = typer.Argument(..., help="Candidate SQL rewrite string or path to .sql file."),
    schema_path: Path = typer.Option(..., "--schema", "-s", help="Path to schema DDL .sql file."),
    config_path: Path = typer.Option(
        Path("sqld.toml"), "--config", "-c", help="Path to sqld.toml configuration."
    ),
    scales: str = typer.Option(
        "1000,10000", "--scales", help="Comma-separated data scales (row counts)."
    ),
    repeats: int = typer.Option(7, "--repeats", help="Number of benchmark repeats per scale."),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw standardized benchmark JSON."
    ),
) -> None:
    """Benchmark performance differences between original query and candidate rewrite."""
    import json

    from sqldoctor.bench.runner import BenchmarkRunner
    from sqldoctor.schema.loader import parse_ddl_to_schema

    orig_sql = original
    cand_sql = candidate
    orig_p = Path(original)
    cand_p = Path(candidate)

    if orig_p.is_file():
        orig_sql = orig_p.read_text(encoding="utf-8")
    if cand_p.is_file():
        cand_sql = cand_p.read_text(encoding="utf-8")

    if not schema_path.is_file():
        typer.secho(f"[-] Schema file not found: {schema_path}", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    ddl_sql = schema_path.read_text(encoding="utf-8")
    schema = parse_ddl_to_schema(ddl_sql)
    scale_list = [int(s.strip()) for s in scales.split(",") if s.strip()]

    runner = BenchmarkRunner(scales=scale_list, repeats=repeats)
    report = runner.run_benchmark(original_sql=orig_sql, candidate_sql=cand_sql, schema=schema)

    if json_output:
        typer.echo(json.dumps(report.model_dump(), indent=2))
    else:
        typer.echo("=" * 60)
        typer.echo("SQL DOCTOR PERFORMANCE BENCHMARK")
        typer.echo("=" * 60)
        typer.echo(f"Primary Metric: {report.primary_metric}")
        typer.echo(f"Overall Buffer Speedup: {report.overall_buffer_speedup}x")
        typer.echo(f"Overall Time Speedup: {report.overall_time_speedup}x")
        if report.is_scale_dependent:
            typer.secho("Warning: Performance is scale-dependent!", fg=typer.colors.YELLOW)

        for s in report.scales:
            typer.echo(
                f"\nScale: {s.scale:,} rows ({s.repeats} repeats)\n"
                f"  Original Buffers (p50): {s.original_buffers_p50} | Time: {s.original_time_ms_p50} ms\n"
                f"  Candidate Buffers (p50): {s.candidate_buffers_p50} | Time: {s.candidate_time_ms_p50} ms\n"
                f"  Buffer Speedup: {s.buffer_speedup_ratio}x | Wall-time Speedup: {s.time_speedup_ratio}x"
            )
        typer.echo(f"\nSummary: {report.summary}")


@app.command("replay")
def replay_receipt_cli(
    receipt_file: Path = typer.Argument(..., help="Path to receipt.sql file to replay."),
    json_output: bool = typer.Option(False, "--json", help="Output raw standardized replay JSON."),
) -> None:
    """Replay a self-contained SQL Doctor receipt and confirm verdict reproduction."""
    import json

    from sqldoctor.receipt.replay import ReceiptReplayer

    if not receipt_file.is_file():
        typer.secho(f"[-] Receipt file not found: {receipt_file}", fg=typer.colors.RED)
        raise typer.Exit(code=3)

    replayer = ReceiptReplayer()
    result = replayer.replay(receipt_file)

    if json_output:
        typer.echo(json.dumps(result.model_dump(), indent=2))
    else:
        if result.matches:
            typer.secho(
                f"[+] REPLAY VERIFIED: {result.observed_verdict} reproduces recorded verdict.",
                fg=typer.colors.GREEN,
                bold=True,
            )
        else:
            typer.secho(
                f"[-] REPLAY MISMATCH: Recorded {result.recorded_verdict}, but observed {result.observed_verdict}!",
                fg=typer.colors.RED,
                bold=True,
            )
            typer.echo(f"Disparities: {result.disparity_count}")

    if result.matches:
        raise typer.Exit(code=0)
    else:
        raise typer.Exit(code=1)


@app.command("eval")
def run_evaluation_cli(
    suite: str = typer.Option(
        "all", "--suite", "-s", help="Suite to evaluate: 'traps', 'good', 'perf', or 'all'."
    ),
    baselines: bool = typer.Option(
        True, "--baselines/--no-baselines", "-b", help="Run comparative baselines (LLM-as-judge, fixed-random)."
    ),
    ablations: bool = typer.Option(
        True, "--ablations/--no-ablations", "-a", help="Run adversary ablations (no_enum, no_fuzz)."
    ),
    out_dir: Path = typer.Option(
        Path("eval/results"), "--out-dir", "-o", help="Directory to save evaluation reports."
    ),
    config_path: Path = typer.Option(
        Path("sqld.toml"), "--config", "-c", help="Path to sqld.toml configuration."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw evaluation report JSON."),
) -> None:
    """Run SQL Doctor evaluation suite across baselines, ablations, and performance benchmarks."""
    import json

    from sqldoctor.agent.llm import LLMClient
    from sqldoctor.eval.runner import EvaluationRunner

    cfg = load_config(config_path)

    # Initialize LLM client if configured
    llm = None
    try:
        llm = LLMClient(
            api_key=cfg.agent.api_key,
            base_url=cfg.agent.base_url,
            model=cfg.agent.model,
            max_cost_usd=cfg.agent.max_cost_usd,
        )
    except Exception:
        pass

    runner = EvaluationRunner(config=cfg, out_dir=out_dir, llm_client=llm)

    typer.echo(f"Starting SQL Doctor evaluation [suite={suite}, baselines={baselines}, ablations={ablations}]...")
    report = runner.run_evaluation(suite=suite, baselines=baselines, ablations=ablations)

    if json_output:
        typer.echo(json.dumps(report.model_dump(), indent=2))
    else:
        typer.echo("\n" + "=" * 60)
        typer.secho("SQL DOCTOR EVALUATION COMPLETE", fg=typer.colors.GREEN, bold=True)
        typer.echo("=" * 60)
        if report.summary_markdown:
            typer.echo(report.summary_markdown)
            typer.echo("")
        typer.echo(f"Results artifacts saved to: {out_dir.resolve()}")

    # Release gate: Fail if SQL Doctor produced any false accepts on the trap suite
    sqld_traps = report.suites.get("sqld_traps")
    if sqld_traps and sqld_traps.false_accepts > 0:
        typer.secho(
            f"[-] RELEASE GATE FAILED: SQL Doctor permitted {sqld_traps.false_accepts} false accepts!",
            fg=typer.colors.RED,
            bold=True,
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
