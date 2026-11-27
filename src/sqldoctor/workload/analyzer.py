"""
@file analyzer.py
@description Workload analyzer orchestrating top-N diagnosis, index consolidation, and HypoPG checks
@module sqldoctor/workload/analyzer
"""

from pathlib import Path

from sqldoctor.agent.loop import DiagnosticAgent
from sqldoctor.config import AppConfig
from sqldoctor.sandbox.client import SandboxClient
from sqldoctor.schema.models import SchemaModel
from sqldoctor.workload.hypopg import HypoPGAdvisor, parse_index_signature
from sqldoctor.workload.models import (
    ConsolidatedIndexCandidate,
    StatStatementEntry,
    WorkloadQueryResult,
    WorkloadReport,
)
from sqldoctor.workload.parser import parse_pg_stat_statements


def consolidate_indexes(
    raw_proposals: list[tuple[str, str, str]],
) -> list[ConsolidatedIndexCandidate]:
    """Deduplicate and merge prefix-redundant CREATE INDEX proposals across queries.

    Args:
        raw_proposals: List of (queryid, index_sql, rationale) tuples.

    Returns:
        Consolidated list of unique, non-prefix-redundant ConsolidatedIndexCandidate items.
    """
    parsed_items: list[tuple[str, str, list[str], str, str]] = []
    for queryid, index_sql, rationale in raw_proposals:
        sig = parse_index_signature(index_sql)
        if not sig:
            continue
        table, cols = sig
        if not cols:
            continue
        parsed_items.append((table, index_sql.strip(), cols, queryid, rationale.strip()))

    # Sort widest column lists first so covering composite indexes subsume strict prefixes
    parsed_items.sort(key=lambda item: len(item[2]), reverse=True)

    kept: list[ConsolidatedIndexCandidate] = []
    for table, idx_sql, cols, queryid, rationale in parsed_items:
        merged = False
        for existing in kept:
            if existing.table != table:
                continue
            # Check exact match or strict leading-column prefix subsumption
            if len(cols) <= len(existing.columns) and existing.columns[: len(cols)] == cols:
                if queryid not in existing.helped_queries:
                    existing.helped_queries.append(queryid)
                if rationale and rationale not in existing.rationale:
                    existing.rationale = (
                        f"{existing.rationale}; {rationale}" if existing.rationale else rationale
                    )
                merged = True
                break
        if not merged:
            kept.append(
                ConsolidatedIndexCandidate(
                    index_sql=idx_sql if idx_sql.endswith(";") else f"{idx_sql};",
                    table=table,
                    columns=cols,
                    rationale=rationale,
                    helped_queries=[queryid],
                )
            )

    return kept


class WorkloadAnalyzer:
    """Ranks pg_stat_statements queries, diagnoses top-N under budget, and verifies indexes."""

    def __init__(
        self,
        config: AppConfig,
        schema: SchemaModel,
        db_client: SandboxClient | None = None,
    ) -> None:
        self.config = config
        self.schema = schema
        self.db_client = db_client
        self.hypopg = HypoPGAdvisor(db_client=db_client)

    def analyze(
        self,
        stats_source: str | Path,
        top_n: int = 5,
        budget_usd: float | None = None,
    ) -> WorkloadReport:
        """Analyze a pg_stat_statements export under a global LLM cost budget."""
        entries = parse_pg_stat_statements(stats_source)
        total_in_export = len(entries)
        selected: list[StatStatementEntry] = entries[: max(top_n, 1)]

        effective_budget = budget_usd if budget_usd is not None else self.config.agent.max_cost_usd
        spent = 0.0
        query_results: list[WorkloadQueryResult] = []
        raw_index_proposals: list[tuple[str, str, str]] = []

        for entry in selected:
            remaining = max(0.0, effective_budget - spent)
            if remaining <= 0.0 and effective_budget > 0.0:
                query_results.append(
                    WorkloadQueryResult(
                        queryid=entry.queryid,
                        total_exec_time_ms=entry.total_exec_time_ms,
                        calls=entry.calls,
                        original_sql=entry.query,
                        verdict="skipped_budget_exhausted",
                        cost_usd=0.0,
                    )
                )
                continue

            scoped_cfg = self.config.model_copy(
                update={"agent": self.config.agent.model_copy(update={"max_cost_usd": remaining})}
            )
            agent = DiagnosticAgent(config=scoped_cfg, schema_model=self.schema)
            diag = agent.run(original_sql=entry.query)
            spent = round(spent + diag.total_cost_usd, 6)

            idx_strs = [idx.index_sql for idx in diag.proposed_indexes]
            for idx in diag.proposed_indexes:
                raw_index_proposals.append((entry.queryid, idx.index_sql, idx.explanation))

            query_results.append(
                WorkloadQueryResult(
                    queryid=entry.queryid,
                    total_exec_time_ms=entry.total_exec_time_ms,
                    calls=entry.calls,
                    original_sql=entry.query,
                    verdict=diag.verdict,
                    best_candidate=diag.best_candidate,
                    proposed_indexes=idx_strs,
                    cost_usd=diag.total_cost_usd,
                )
            )

        consolidated = consolidate_indexes(raw_index_proposals)
        evaluated_indexes: list[ConsolidatedIndexCandidate] = [
            self.hypopg.evaluate_index(idx, selected, self.schema) for idx in consolidated
        ]

        reduction_pct = 0.0
        if evaluated_indexes:
            best_before = max((c.estimated_cost_before or 0.0) for c in evaluated_indexes)
            best_after = min((c.estimated_cost_after or best_before) for c in evaluated_indexes)
            if best_before > 0.0:
                reduction_pct = round(max(0.0, (best_before - best_after) / best_before * 100.0), 1)

        mode_label = "HypoPG (live PG17)" if self.db_client is not None else "offline heuristic"
        summary = (
            f"Analyzed top {len(selected)}/{total_in_export} queries "
            f"(LLM spend ${spent:.4f}/${effective_budget:.2f}); "
            f"consolidated {len(raw_index_proposals)} index proposals into "
            f"{len(evaluated_indexes)} unique index(es) via {mode_label} "
            f"(est. cost reduction {reduction_pct}%)."
        )

        return WorkloadReport(
            total_queries_in_export=total_in_export,
            top_n_analyzed=len(selected),
            total_cost_usd=spent,
            budget_usd=effective_budget,
            query_results=query_results,
            consolidated_indexes=evaluated_indexes,
            overall_hypopg_cost_reduction_pct=reduction_pct,
            summary=summary,
        )
