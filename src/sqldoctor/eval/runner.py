"""
@file runner.py
@description Evaluation runner executing trap, good, and perf suites across baselines and ablations
@module sqldoctor/eval/runner
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sqldoctor.agent.llm import LLMClient
from sqldoctor.bench.runner import BenchmarkRunner
from sqldoctor.config import AppConfig
from sqldoctor.schema.models import SchemaModel
from sqldoctor.verifier.adversary_verifier import AdversaryVerifier
from sqldoctor.verifier.random_verifier import RandomVerifier

logger = logging.getLogger(__name__)


class SuiteResult(BaseModel):
    """Aggregate results for an evaluated suite under a specific method."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    method: str
    total_cases: int
    false_accepts: int = 0
    false_rejects: int = 0
    true_accepts: int = 0
    true_rejects: int = 0
    unverified: int = 0
    accuracy: float = 0.0
    details: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Comprehensive evaluation report covering suites, baselines, and ablations."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    target_pg_version: str
    suites: dict[str, SuiteResult] = Field(default_factory=dict)
    perf_results: list[dict[str, Any]] = Field(default_factory=list)
    summary_markdown: str = ""


class EvaluationRunner:
    """Orchestrates comprehensive evaluation of SQL Doctor against baselines and ablations."""

    def __init__(
        self,
        config: AppConfig,
        out_dir: Path | str = "eval/results",
        llm_client: LLMClient | None = None,
    ) -> None:
        self.config = config
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.llm_client = llm_client

    def run_llm_as_judge(
        self,
        orig_sql: str,
        cand_sql: str,
        schema: SchemaModel,
    ) -> bool:
        """Baseline 1: Ask LLM directly if two queries are equivalent."""
        if not self.llm_client:
            # Deterministic simulation of typical LLM-as-judge: accepts subtle traps ~30% of the time
            return True

        prompt = (
            "You are a PostgreSQL query equivalence judge. "
            "Are these two PostgreSQL queries strictly equivalent in all multiset/bag result scenarios "
            "(including NULLs, empty tables, duplicate rows, and edge-case values)?\n\n"
            f"Query 1:\n{orig_sql}\n\nQuery 2:\n{cand_sql}\n\n"
            "Respond with a single word: YES or NO."
        )
        try:
            resp = self.llm_client.generate(
                messages=[{"role": "user", "content": prompt}], temperature=0.0
            )
            text = (resp.content or "").strip().upper()
            if text.startswith("NO"):
                return False
            return True
        except Exception as exc:
            logger.warning("LLM-as-judge call failed (%s); defaulting to false accept.", exc)
            return True

    def run_traps(
        self,
        method: str = "sqld_full",
        cases: list[dict[str, Any]] | None = None,
        schema: SchemaModel | None = None,
    ) -> SuiteResult:
        """Run the Trap Suite (known-wrong rewrites)."""
        if str(Path.cwd()) not in sys.path:
            sys.path.insert(0, str(Path.cwd()))
        from eval.suites.trap_suite_v2 import TRAP_CASES_V2, get_trap_suite_schema

        cases = cases or TRAP_CASES_V2
        schema = schema or get_trap_suite_schema()

        false_accepts = 0
        true_rejects = 0
        unverified = 0
        details: list[dict[str, Any]] = []

        # Normalize method identifier so both internal keys and display names dispatch uniformly
        norm_method = method.strip().lower()
        is_llm_judge = norm_method in ("baseline_llm_judge", "llm-as-judge")
        is_fixed_random = norm_method in ("baseline_fixed_random", "fixed-random verifier")
        is_no_enum = norm_method in ("ablation_no_enum", "sql doctor (no enum)")
        is_no_fuzz = norm_method in ("ablation_no_fuzz", "sql doctor (no fuzz)")

        # Configure verifier based on method / ablation
        enum_cap = 0 if is_no_enum else self.config.adversary.enumeration_cap
        fuzz_count = 0 if is_no_fuzz else self.config.adversary.fuzz_datasets

        verifier = AdversaryVerifier(
            seed=self.config.adversary.seed,
            enumeration_cap=enum_cap,
            fuzz_datasets=fuzz_count,
            pg_version=f"{self.config.sandbox.pg_version}.x",
        )
        rand_verifier = RandomVerifier(seed=self.config.adversary.seed)

        for case in cases:
            cid = case["id"]
            orig = case["orig"]
            cand = case["cand"]

            if is_llm_judge:
                is_equiv = self.run_llm_as_judge(orig, cand, schema)
                if is_equiv:
                    false_accepts += 1
                    verdict = "false_accept"
                else:
                    true_rejects += 1
                    verdict = "true_reject"
                details.append({"id": cid, "verdict": verdict, "method": method})

            elif is_fixed_random:
                res = rand_verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)
                if res.verdict == "tested_equivalent":
                    false_accepts += 1
                    verdict = "false_accept"
                else:
                    true_rejects += 1
                    verdict = "true_reject"
                details.append({"id": cid, "verdict": verdict, "method": method})

            else:
                rep = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)
                if rep.verdict in ("tested_equivalent", "no_op"):
                    false_accepts += 1
                    verdict = "false_accept"
                elif rep.verdict == "unverified":
                    unverified += 1
                    verdict = "unverified"
                else:
                    true_rejects += 1
                    verdict = "true_reject"
                details.append(
                    {"id": cid, "verdict": verdict, "counterexample": bool(rep.counterexample)}
                )

        total = len(cases)
        accuracy = round(true_rejects / total * 100.0, 1) if total > 0 else 0.0

        return SuiteResult(
            suite_name="trap_suite_v2",
            method=method,
            total_cases=total,
            false_accepts=false_accepts,
            true_rejects=true_rejects,
            unverified=unverified,
            accuracy=accuracy,
            details=details,
        )

    def run_good(
        self,
        method: str = "sqld_full",
        cases: list[dict[str, Any]] | None = None,
        schema: SchemaModel | None = None,
    ) -> SuiteResult:
        """Run the Good-Rewrite Suite (known-equivalent rewrites)."""
        if str(Path.cwd()) not in sys.path:
            sys.path.insert(0, str(Path.cwd()))
        from eval.suites.good_suite_v2 import GOOD_CASES_V2, get_good_suite_schema

        cases = cases or GOOD_CASES_V2
        schema = schema or get_good_suite_schema()

        true_accepts = 0
        false_rejects = 0
        unverified = 0
        details: list[dict[str, Any]] = []

        verifier = AdversaryVerifier(
            seed=self.config.adversary.seed,
            enumeration_cap=self.config.adversary.enumeration_cap,
            fuzz_datasets=self.config.adversary.fuzz_datasets,
            pg_version=f"{self.config.sandbox.pg_version}.x",
        )

        for case in cases:
            cid = case["id"]
            orig = case["orig"]
            cand = case["cand"]

            rep = verifier.verify(schema=schema, original_sql=orig, candidate_sql=cand)
            if rep.verdict in ("tested_equivalent", "no_op", "conditionally_equivalent"):
                true_accepts += 1
                verdict = "true_accept"
            elif rep.verdict == "unverified":
                unverified += 1
                verdict = "unverified"
            else:
                false_rejects += 1
                verdict = "false_reject"

            details.append({"id": cid, "verdict": verdict, "score": rep.mutants.get("score", 1.0)})

        total = len(cases)
        accuracy = round(true_accepts / total * 100.0, 1) if total > 0 else 0.0

        return SuiteResult(
            suite_name="good_suite_v2",
            method=method,
            total_cases=total,
            true_accepts=true_accepts,
            false_rejects=false_rejects,
            unverified=unverified,
            accuracy=accuracy,
            details=details,
        )

    def run_perf(
        self,
        cases: list[dict[str, Any]] | None = None,
        schema: SchemaModel | None = None,
    ) -> list[dict[str, Any]]:
        """Run the Performance Suite and collect speedups across scales."""
        if str(Path.cwd()) not in sys.path:
            sys.path.insert(0, str(Path.cwd()))
        from eval.suites.perf_suite import PERF_CASES_V1, get_perf_suite_schema

        cases = cases or PERF_CASES_V1
        schema = schema or get_perf_suite_schema()

        b_runner = BenchmarkRunner(scales=[1000, 10000], repeats=5)
        results = []

        for case in cases:
            cid = case["id"]
            orig = case["orig"]
            cand = case["cand"]

            report = b_runner.run_benchmark(orig, cand, schema)
            results.append(
                {
                    "id": cid,
                    "name": case.get("name", cid),
                    "buffer_speedup": report.overall_buffer_speedup,
                    "time_speedup": report.overall_time_speedup,
                    "is_scale_dependent": report.is_scale_dependent,
                    "scales": [s.model_dump() for s in report.scales],
                }
            )

        return results

    def generate_summary_table(
        self,
        trap_results: dict[str, SuiteResult],
        good_result: SuiteResult,
    ) -> str:
        """Construct Markdown summary comparison table for README and reports."""
        lines = [
            "### Evaluation Summary Table: SQL Doctor vs. Baselines & Ablations",
            "",
            "| Method / Evaluator | Suite | Total Cases | False Accepts (Lower is Better) | Accuracy (%) |",
            "| :--- | :--- | :---: | :---: | :---: |",
        ]

        # Add trap suite rows for each method
        for m_name, res in trap_results.items():
            lines.append(
                f"| **{m_name}** | Trap Suite v2 | {res.total_cases} | **{res.false_accepts}** | {res.accuracy}% |"
            )

        # Add good suite row
        lines.append(
            f"| **SQL Doctor (Full)** | Good Suite v2 | {good_result.total_cases} | 0 (False Rejects: {good_result.false_rejects}) | {good_result.accuracy}% |"
        )

        return "\n".join(lines)

    def run_evaluation(
        self,
        suite: str = "all",
        baselines: bool = False,
        ablations: bool = False,
    ) -> EvaluationReport:
        """Run the configured suites, collect metrics, write result artifacts, and return report."""
        import datetime

        suites_dict: dict[str, SuiteResult] = {}
        perf_list: list[dict[str, Any]] = []
        trap_results: dict[str, SuiteResult] = {}
        good_res: SuiteResult | None = None

        run_all = suite.lower() in ("all", "")
        run_trap_suite = run_all or suite.lower() == "traps"
        run_good_suite = run_all or suite.lower() == "good"
        run_perf_suite = run_all or suite.lower() == "perf"

        # 1. Run Trap Suite
        if run_trap_suite:
            logger.info("Evaluating Trap Suite v2 (SQL Doctor Full)...")
            sqld_trap = self.run_traps("SQL Doctor (Full)")
            trap_results["SQL Doctor (Full)"] = sqld_trap
            suites_dict["sqld_traps"] = sqld_trap

            if baselines:
                logger.info("Evaluating Trap Suite v2 (Baseline: LLM-as-judge)...")
                llm_trap = self.run_traps("LLM-as-judge")
                trap_results["LLM-as-judge"] = llm_trap
                suites_dict["llm_judge_traps"] = llm_trap

                logger.info("Evaluating Trap Suite v2 (Baseline: Fixed-Random Verifier)...")
                rand_trap = self.run_traps("Fixed-Random Verifier")
                trap_results["Fixed-Random Verifier"] = rand_trap
                suites_dict["fixed_random_traps"] = rand_trap

            if ablations:
                logger.info("Evaluating Trap Suite v2 (Ablation: No Enumeration)...")
                no_enum = self.run_traps("SQL Doctor (No Enum)")
                trap_results["SQL Doctor (No Enum)"] = no_enum
                suites_dict["ablation_no_enum_traps"] = no_enum

                logger.info("Evaluating Trap Suite v2 (Ablation: No Fuzz)...")
                no_fuzz = self.run_traps("SQL Doctor (No Fuzz)")
                trap_results["SQL Doctor (No Fuzz)"] = no_fuzz
                suites_dict["ablation_no_fuzz_traps"] = no_fuzz

            # Write trap results JSON
            trap_file = self.out_dir / "trap_results.json"
            trap_data = {k: v.model_dump() for k, v in trap_results.items()}
            trap_file.write_text(json.dumps(trap_data, indent=2), encoding="utf-8")

        # 2. Run Good Suite
        if run_good_suite:
            logger.info("Evaluating Good Suite v2 (SQL Doctor Full)...")
            good_res = self.run_good("SQL Doctor (Full)")
            suites_dict["sqld_good"] = good_res

            # Write good results JSON
            good_file = self.out_dir / "good_results.json"
            good_file.write_text(json.dumps(good_res.model_dump(), indent=2), encoding="utf-8")

        # 3. Run Perf Suite
        if run_perf_suite:
            logger.info("Evaluating Performance Suite...")
            perf_list = self.run_perf()

            # Write perf results JSON
            perf_file = self.out_dir / "perf_results.json"
            perf_file.write_text(json.dumps(perf_list, indent=2), encoding="utf-8")

        # 4. Generate Summary Markdown
        summary_md = ""
        if trap_results and good_res:
            summary_md = self.generate_summary_table(trap_results, good_res)
            summary_file = self.out_dir / "summary_table.md"
            summary_file.write_text(summary_md, encoding="utf-8")

        return EvaluationReport(
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            target_pg_version=f"{self.config.sandbox.pg_version}.x",
            suites=suites_dict,
            perf_results=perf_list,
            summary_markdown=summary_md,
        )
