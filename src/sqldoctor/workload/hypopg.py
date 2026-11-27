"""
@file hypopg.py
@description HypoPG hypothetical index planner evaluation for Phase 9 Workload Mode
@module sqldoctor/workload/hypopg
"""

import json
import logging
import re
from typing import Any

from sqldoctor.sandbox.client import SandboxClient
from sqldoctor.schema.models import SchemaModel
from sqldoctor.workload.models import ConsolidatedIndexCandidate, StatStatementEntry

logger = logging.getLogger(__name__)

_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\w+\s+)?ON\s+([a-zA-Z_][\w.]*)\s*\(([^)]+)\)",
    re.IGNORECASE,
)


def parse_index_signature(index_sql: str) -> tuple[str, list[str]] | None:
    """Extract target table and ordered column list from a CREATE INDEX statement."""
    match = _CREATE_INDEX_RE.search(index_sql)
    if not match:
        return None
    table = match.group(1).split(".")[-1].strip('"').lower()
    raw_cols = match.group(2)
    cols = [c.strip().strip('"').split()[0].lower() for c in raw_cols.split(",") if c.strip()]
    return table, cols


def _extract_total_cost(explain_rows: list[tuple[Any, ...]]) -> float:
    """Extract Total Cost from PostgreSQL EXPLAIN (FORMAT JSON) output."""
    if not explain_rows or not explain_rows[0]:
        return 0.0
    payload = explain_rows[0][0]
    parsed = json.loads(payload) if isinstance(payload, str) else payload
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    plan = parsed.get("Plan", {}) if isinstance(parsed, dict) else {}
    return float(plan.get("Total Cost", 0.0))


class HypoPGAdvisor:
    """Evaluates consolidated index candidates across workload queries via HypoPG."""

    def __init__(self, db_client: SandboxClient | None = None) -> None:
        self.db_client = db_client

    def _ensure_sandbox_ready(self, schema: SchemaModel) -> None:
        """Ensure HypoPG extension and schema tables exist in the sandbox."""
        assert self.db_client is not None
        self.db_client.execute_script("CREATE EXTENSION IF NOT EXISTS hypopg;")
        for tname, tmodel in schema.tables.items():
            col_defs = [f'"{cname}" {cmodel.data_type}' for cname, cmodel in tmodel.columns.items()]
            self.db_client.execute_script(
                f'CREATE TABLE IF NOT EXISTS "{tname}" ({", ".join(col_defs)});'
            )

    def evaluate_index(
        self,
        candidate: ConsolidatedIndexCandidate,
        queries: list[StatStatementEntry],
        schema: SchemaModel,
    ) -> ConsolidatedIndexCandidate:
        """Evaluate a consolidated index across all workload queries.

        Uses live PostgreSQL + HypoPG when a SandboxClient is connected, and falls back
        to a deterministic AST/column heuristic when running offline.
        """
        if self.db_client is not None:
            try:
                return self._evaluate_live_hypopg(candidate, queries, schema)
            except Exception as exc:
                logger.warning("Live HypoPG evaluation failed (%s); falling back offline.", exc)

        return self._evaluate_offline(candidate, queries)

    def _evaluate_live_hypopg(
        self,
        candidate: ConsolidatedIndexCandidate,
        queries: list[StatStatementEntry],
        schema: SchemaModel,
    ) -> ConsolidatedIndexCandidate:
        """Measure planner Total Cost delta across queries using real HypoPG."""
        assert self.db_client is not None
        self._ensure_sandbox_ready(schema)

        before_costs: dict[str, float] = {}
        for entry in queries:
            sql_clean = entry.query.strip().rstrip(";")
            rows = self.db_client.execute_query(f"EXPLAIN (FORMAT JSON) {sql_clean};")
            before_costs[entry.queryid] = _extract_total_cost(rows)

        after_costs: dict[str, float] = {}
        self.db_client.execute_query("SELECT hypopg_reset();")
        try:
            idx_sql = candidate.index_sql.strip().rstrip(";")
            self.db_client.execute_query("SELECT * FROM hypopg_create_index(%s);", (idx_sql,))
            for entry in queries:
                sql_clean = entry.query.strip().rstrip(";")
                rows = self.db_client.execute_query(f"EXPLAIN (FORMAT JSON) {sql_clean};")
                after_costs[entry.queryid] = _extract_total_cost(rows)
        finally:
            self.db_client.execute_query("SELECT hypopg_reset();")

        helped: list[str] = []
        regressed: list[str] = []
        for entry in queries:
            b_cost = before_costs.get(entry.queryid, 0.0)
            a_cost = after_costs.get(entry.queryid, b_cost)
            if a_cost < b_cost:
                helped.append(entry.queryid)
            elif a_cost > b_cost:
                regressed.append(entry.queryid)

        total_before = round(sum(before_costs.values()), 2)
        total_after = round(sum(after_costs.values()), 2)

        return candidate.model_copy(
            update={
                "helped_queries": sorted(set(candidate.helped_queries) | set(helped)),
                "regressed_queries": regressed,
                "hypopg_plan_changed": total_after < total_before or bool(helped),
                "estimated_cost_before": total_before,
                "estimated_cost_after": total_after,
                "verified_in_sandbox": True,
            }
        )

    def _evaluate_offline(
        self,
        candidate: ConsolidatedIndexCandidate,
        queries: list[StatStatementEntry],
    ) -> ConsolidatedIndexCandidate:
        """Deterministic offline planner cost estimate based on table/column references."""
        helped: list[str] = []
        total_before = 0.0
        total_after = 0.0

        for entry in queries:
            q_lower = entry.query.lower()
            base_cost = max(entry.total_exec_time_ms, 10.0)
            total_before += base_cost

            uses_table = bool(re.search(rf"\b{re.escape(candidate.table)}\b", q_lower))
            uses_lead_col = bool(
                candidate.columns and re.search(rf"\b{re.escape(candidate.columns[0])}\b", q_lower)
            )
            if uses_table and uses_lead_col:
                helped.append(entry.queryid)
                total_after += base_cost * 0.45
            else:
                total_after += base_cost

        return candidate.model_copy(
            update={
                "helped_queries": sorted(set(candidate.helped_queries) | set(helped)),
                "regressed_queries": [],
                "hypopg_plan_changed": bool(helped),
                "estimated_cost_before": round(total_before, 2),
                "estimated_cost_after": round(total_after, 2),
                "verified_in_sandbox": False,
            }
        )
