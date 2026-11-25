"""
@file test_evaluation.py
@description Comprehensive tests for Phase 5 evaluation suite: Trap Suite v2, Good Suite v2, and EvaluationRunner
@module tests/test_evaluation
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from eval.suites.good_suite_v2 import GOOD_CASES_V2, get_good_suite_schema
from eval.suites.perf_suite import PERF_CASES_V1
from eval.suites.trap_suite_v2 import TRAP_CASES_V2, get_trap_suite_schema
from sqldoctor.config import AppConfig
from sqldoctor.eval.runner import EvaluationRunner


def test_trap_suite_v2_zero_false_accepts() -> None:
    """Non-negotiable release gate: Zero false accepts across all 50 Trap Suite v2 cases."""
    cfg = AppConfig()
    runner = EvaluationRunner(config=cfg)

    result = runner.run_traps(method="SQL Doctor (Full)")

    assert result.total_cases == 50
    # Strict release gate requirement from build plan:
    assert result.false_accepts == 0, f"Expected 0 false accepts, got {result.false_accepts}"
    assert result.true_rejects == 50
    assert result.accuracy == 100.0


def test_good_suite_v2_accuracy() -> None:
    """Validate that Good Suite v2 achieves high true-acceptance rate on known-equivalent queries."""
    cfg = AppConfig()
    runner = EvaluationRunner(config=cfg)

    result = runner.run_good(method="SQL Doctor (Full)")

    assert result.total_cases == 30
    # Must accept at least 90% (>= 27/30) without false rejections
    assert result.true_accepts >= 27
    assert result.false_rejects <= 3


def test_baselines_detection_gaps() -> None:
    """Validate that LLM-as-judge baseline permits false accepts on subtle traps."""
    cfg = AppConfig()
    runner = EvaluationRunner(config=cfg)

    # Test LLM-as-judge baseline on traps
    llm_result = runner.run_traps(method="baseline_llm_judge")
    assert llm_result.total_cases == 50
    # LLM-as-judge misses subtle semantic traps (the core problem solved by SQL Doctor)
    assert llm_result.false_accepts > 0


def test_perf_suite_simulation() -> None:
    """Validate that performance suite benchmarks all 30 queries across scales."""
    cfg = AppConfig()
    runner = EvaluationRunner(config=cfg)

    # Run first 5 perf queries for quick unit verification
    results = runner.run_perf(cases=PERF_CASES_V1[:5])
    assert len(results) == 5
    for r in results:
        assert "buffer_speedup" in r
        assert "time_speedup" in r
        assert len(r["scales"]) == 2


def test_evaluation_runner_full_workflow() -> None:
    """Verify that EvaluationRunner writes all JSON artifacts and summary markdown."""
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cfg = AppConfig()
        runner = EvaluationRunner(config=cfg, out_dir=tmp_path)

        # Run minimal subset across suites for speed
        schema_trap = get_trap_suite_schema()
        schema_good = get_good_suite_schema()

        trap_sub = TRAP_CASES_V2[:5]
        good_sub = GOOD_CASES_V2[:5]

        res_trap = runner.run_traps("SQL Doctor (Full)", cases=trap_sub, schema=schema_trap)
        res_good = runner.run_good("SQL Doctor (Full)", cases=good_sub, schema=schema_good)

        md = runner.generate_summary_table({"SQL Doctor (Full)": res_trap}, res_good)

        assert "Trap Suite v2" in md
        assert "Good Suite v2" in md
        assert "| **SQL Doctor (Full)** |" in md
