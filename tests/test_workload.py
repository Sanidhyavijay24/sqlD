"""
@file test_workload.py
@description Unit and CLI tests for Phase 9 Workload Mode (pg_stat_statements, index consolidation, HypoPG)
@module tests/test_workload
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sqldoctor.agent.loop import DiagnosticResult, IndexProposal
from sqldoctor.cli import app
from sqldoctor.config import AppConfig
from sqldoctor.schema.loader import parse_ddl_to_schema
from sqldoctor.workload.analyzer import WorkloadAnalyzer, consolidate_indexes
from sqldoctor.workload.hypopg import HypoPGAdvisor
from sqldoctor.workload.models import ConsolidatedIndexCandidate, StatStatementEntry
from sqldoctor.workload.parser import parse_pg_stat_statements

runner = CliRunner()

SAMPLE_DDL = """
CREATE TABLE customers (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(50) NOT NULL,
    is_vip BOOLEAN NOT NULL
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    amount NUMERIC NOT NULL,
    status VARCHAR(20) NOT NULL
);
"""


def test_parse_pg_stat_statements_json_and_csv() -> None:
    """Verify JSON and CSV exports are filtered and ranked descending by total_exec_time_ms."""
    json_entries = parse_pg_stat_statements(Path("examples/pg_stat_statements.json"))
    assert len(json_entries) == 3  # COMMIT filtered out
    assert json_entries[0].queryid == "1001"
    assert json_entries[1].queryid == "1002"
    assert json_entries[2].queryid == "1003"

    csv_data = (
        "queryid,query,calls,total_time\n"
        '1,"SELECT * FROM pg_stat_statements;",10,500.0\n'
        '2,"SELECT id FROM customers;",5,120.0\n'
        '3,"SELECT id FROM orders;",20,900.0\n'
    )
    csv_entries = parse_pg_stat_statements(csv_data)
    assert [e.queryid for e in csv_entries] == ["3", "2"]
    assert csv_entries[0].total_exec_time_ms == 900.0


def test_consolidate_indexes_prefix_subsumption() -> None:
    """Verify narrower prefix indexes are subsumed by wider composite indexes."""
    proposals = [
        (
            "1002",
            "CREATE INDEX idx_orders_status ON orders (status);",
            "Filter by status",
        ),
        (
            "1001",
            "CREATE INDEX idx_orders_status_cust_amt ON orders (status, customer_id, amount);",
            "Covering index",
        ),
        (
            "1003",
            "CREATE INDEX idx_cust_country_vip ON customers (country, is_vip);",
            "VIP country lookup",
        ),
    ]
    consolidated = consolidate_indexes(proposals)
    assert len(consolidated) == 2
    orders_idx = next(c for c in consolidated if c.table == "orders")
    assert orders_idx.columns == ["status", "customer_id", "amount"]
    assert set(orders_idx.helped_queries) == {"1001", "1002"}


def test_hypopg_advisor_mocked_sandbox() -> None:
    """Verify HypoPGAdvisor runs hypopg_create_index, EXPLAIN JSON, and hypopg_reset."""
    scripts: list[str] = []
    queries_called: list[str] = []
    hypopg_active = False

    class MockSandboxClient:
        def execute_script(self, sql: str) -> None:
            scripts.append(sql)

        def execute_query(
            self, sql: str, params: tuple[Any, ...] | None = None
        ) -> list[tuple[Any, ...]]:
            nonlocal hypopg_active
            queries_called.append(sql)
            if "hypopg_create_index" in sql:
                hypopg_active = True
                return [(1, "idx")]
            if "hypopg_reset" in sql:
                hypopg_active = False
                return [(True,)]
            if "EXPLAIN (FORMAT JSON)" in sql:
                if "1001" in sql or "orders" in sql:
                    cost = 12.5 if hypopg_active else 250.0
                else:
                    cost = 20.0
                return [(json.dumps([{"Plan": {"Total Cost": cost}}]),)]
            return []

    schema = parse_ddl_to_schema(SAMPLE_DDL)
    advisor = HypoPGAdvisor(db_client=MockSandboxClient())  # type: ignore[arg-type]
    cand = ConsolidatedIndexCandidate(
        index_sql="CREATE INDEX idx_orders_status ON orders (status);",
        table="orders",
        columns=["status"],
        helped_queries=["1001"],
    )
    entries = [
        StatStatementEntry(
            queryid="1001",
            query="SELECT id FROM orders WHERE status = 'completed';",
            calls=10,
            total_exec_time_ms=1000.0,
        ),
        StatStatementEntry(
            queryid="1003",
            query="SELECT id FROM customers WHERE is_vip = TRUE;",
            calls=5,
            total_exec_time_ms=100.0,
        ),
    ]
    res = advisor.evaluate_index(cand, entries, schema)
    assert res.verified_in_sandbox is True
    assert res.hypopg_plan_changed is True
    assert res.estimated_cost_before == 270.0
    assert res.estimated_cost_after == 32.5
    assert "1001" in res.helped_queries
    assert res.regressed_queries == []
    assert any("hypopg_reset" in q for q in queries_called)


def test_workload_analyzer_budget_and_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify WorkloadAnalyzer enforces global budget and `sqld workload --json` works."""

    class DummyAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def run(self, original_sql: str) -> DiagnosticResult:
            idx = (
                [
                    IndexProposal(
                        index_sql="CREATE INDEX idx_orders_status_cust ON orders (status, customer_id);",
                        explanation="Speed up orders lookup",
                    )
                ]
                if "orders" in original_sql.lower()
                else []
            )
            return DiagnosticResult(
                original_sql=original_sql,
                verdict="tested_equivalent",
                best_candidate=original_sql,
                proposed_indexes=idx,
                total_cost_usd=0.60,
            )

    monkeypatch.setattr("sqldoctor.workload.analyzer.DiagnosticAgent", DummyAgent)

    schema = parse_ddl_to_schema(SAMPLE_DDL)
    cfg = AppConfig()
    analyzer = WorkloadAnalyzer(config=cfg, schema=schema)
    report = analyzer.analyze("examples/pg_stat_statements.json", top_n=3, budget_usd=1.00)

    assert report.total_queries_in_export == 3
    assert report.top_n_analyzed == 3
    # 1st costs 0.60, 2nd costs 0.60 -> 1.20 > 1.00 -> 3rd skipped due to exhausted budget
    assert report.query_results[2].verdict == "skipped_budget_exhausted"
    assert len(report.consolidated_indexes) == 1

    # Verify CLI --help
    help_res = runner.invoke(app, ["workload", "--help"])
    assert help_res.exit_code == 0
    clean_help = re.sub(r"\x1b\[[0-9;]*m", "", help_res.output)
    assert "pg_stat_statements" in clean_help

    # Verify CLI JSON execution
    out_json = tmp_path / "workload.json"
    cli_res = runner.invoke(
        app,
        [
            "workload",
            "examples/pg_stat_statements.json",
            "--schema",
            "examples/schema.sql",
            "--top",
            "2",
            "--budget",
            "2.0",
            "--out",
            str(out_json),
            "--json",
        ],
    )
    assert cli_res.exit_code == 0
    assert out_json.is_file()
    parsed = json.loads(cli_res.stdout)
    assert parsed["top_n_analyzed"] == 2
