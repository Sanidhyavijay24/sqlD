"""
@file test_bench.py
@description Unit and CLI tests for benchmark harness and buffer metrics extraction
@module tests/test_bench
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from sqldoctor.bench.runner import BenchmarkRunner, extract_plan_buffers_and_time
from sqldoctor.cli import app

runner = CliRunner()


def test_plan_buffers_and_time_extraction() -> None:
    """Verify recursive buffer extraction sums hit and read blocks across nested plan nodes."""
    sample_plan = [
        {
            "Plan": {
                "Node Type": "Hash Join",
                "Shared Hit Blocks": 12,
                "Shared Read Blocks": 4,
                "Actual Total Time": 1.45,
                "Plans": [
                    {
                        "Node Type": "Seq Scan",
                        "Shared Hit Blocks": 5,
                        "Shared Read Blocks": 1,
                    },
                    {
                        "Node Type": "Hash",
                        "Shared Hit Blocks": 0,
                        "Shared Read Blocks": 0,
                        "Plans": [
                            {
                                "Node Type": "Index Scan",
                                "Shared Hit Blocks": 8,
                                "Shared Read Blocks": 2,
                            }
                        ],
                    },
                ],
            },
            "Execution Time": 1.85,
        }
    ]

    total_buf, exec_time = extract_plan_buffers_and_time(sample_plan)
    # Total hits: 12 + 5 + 8 = 25. Total reads: 4 + 1 + 2 = 7. Total buffers: 32.
    assert total_buf == 32
    assert exec_time == 1.85


def test_benchmark_runner_multi_scale() -> None:
    """Verify BenchmarkRunner calculates medians and speedup ratios across scales."""
    orig = "SELECT c.id, o.amount FROM customers c, orders o WHERE c.id = o.customer_id;"
    cand = "SELECT c.id, o.amount FROM customers c INNER JOIN orders o ON c.id = o.customer_id;"

    b_runner = BenchmarkRunner(scales=[1000, 10000], repeats=5)
    report = b_runner.run_benchmark(orig, cand)

    assert len(report.scales) == 2
    assert report.scales[0].scale == 1000
    assert report.scales[1].scale == 10000
    assert report.primary_metric == "shared_buffers_hit_plus_read"
    assert report.overall_buffer_speedup > 0.0
    assert report.overall_time_speedup > 0.0
    assert report.summary != ""


def test_cli_bench(tmp_path: Path) -> None:
    """Verify sqld bench CLI command works with --schema and --json."""
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE t (id INT PRIMARY KEY, val INT);", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "bench",
            "SELECT id, val FROM t WHERE val >= 10 AND val <= 20;",
            "SELECT id, val FROM t WHERE val BETWEEN 10 AND 20;",
            "--schema",
            str(schema_file),
            "--scales",
            "500,2000",
            "--repeats",
            "3",
            "--json",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["scales"]) == 2
    assert data["primary_metric"] == "shared_buffers_hit_plus_read"
