"""
@file generator.py
@description Static HTML report generator rendering query diffs, benchmarks, and minimal counterexamples
@module sqldoctor/report/generator
"""

import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from sqldoctor import __version__
from sqldoctor.bench.models import BenchmarkReport
from sqldoctor.verifier.adversary_verifier import AdversaryVerdictReport


class HTMLReportGenerator:
    """Renders standalone, zero-dependency static HTML reports for SQL Doctor verification runs."""

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        self.templates_dir = Path(templates_dir)
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True,
        )

    def render(
        self,
        original_sql: str,
        candidate_sql: str,
        verdict_report: AdversaryVerdictReport,
        benchmark_report: BenchmarkReport | None = None,
        proposed_indexes: list[Any] | None = None,
        explanation: str = "",
        pg_version: str = "17.x",
    ) -> str:
        """Render complete HTML report document string.

        Args:
            original_sql: Reference SQL query.
            candidate_sql: Candidate rewritten SQL query.
            verdict_report: Adversary verdict report.
            benchmark_report: Optional performance benchmark metrics.
            proposed_indexes: Optional list of proposed indexes.
            explanation: Diagnostic explanation or rationale.
            pg_version: PostgreSQL version string.

        Returns:
            HTML string.
        """
        template = self.env.get_template("report.html.j2")
        now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        context = {
            "title": f"SQL Doctor Report — {verdict_report.verdict.upper()}",
            "verdict": verdict_report.verdict.upper(),
            "tool_version": __version__,
            "pg_version": pg_version,
            "seed": verdict_report.seed,
            "timestamp": now,
            "original_sql": original_sql.strip(),
            "candidate_sql": candidate_sql.strip(),
            "explanation": explanation.strip(),
            "counterexample": verdict_report.counterexample.model_dump()
            if verdict_report.counterexample
            else None,
            "benchmark": benchmark_report.model_dump() if benchmark_report else None,
            "proposed_indexes": proposed_indexes or [],
            "mutants": verdict_report.mutants,
            "datasets": verdict_report.datasets,
        }

        return template.render(context)

    def write_report(
        self,
        output_path: Path | str,
        original_sql: str,
        candidate_sql: str,
        verdict_report: AdversaryVerdictReport,
        benchmark_report: BenchmarkReport | None = None,
        proposed_indexes: list[Any] | None = None,
        explanation: str = "",
        pg_version: str = "17.x",
    ) -> Path:
        """Render and save HTML report to file.

        Args:
            output_path: Destination path for .html file.
            original_sql: Reference SQL query.
            candidate_sql: Candidate rewritten SQL query.
            verdict_report: Adversary verdict report.
            benchmark_report: Optional performance benchmark metrics.
            proposed_indexes: Optional list of proposed indexes.
            explanation: Diagnostic explanation or rationale.
            pg_version: PostgreSQL version string.

        Returns:
            Resolved Path of generated HTML report.
        """
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        html_content = self.render(
            original_sql=original_sql,
            candidate_sql=candidate_sql,
            verdict_report=verdict_report,
            benchmark_report=benchmark_report,
            proposed_indexes=proposed_indexes,
            explanation=explanation,
            pg_version=pg_version,
        )
        p.write_text(html_content, encoding="utf-8")
        return p
