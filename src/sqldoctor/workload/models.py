"""
@file models.py
@description Strict Pydantic models for Phase 9 Workload Mode
@module sqldoctor/workload/models
"""

from pydantic import BaseModel, ConfigDict, Field


class StatStatementEntry(BaseModel):
    """Single normalized entry from a pg_stat_statements export."""

    model_config = ConfigDict(extra="forbid")

    queryid: str = Field(description="Statement identifier from pg_stat_statements")
    query: str = Field(min_length=1, description="SQL query text")
    calls: int = Field(ge=0, default=1, description="Number of executions")
    total_exec_time_ms: float = Field(
        ge=0.0, description="Total execution time in milliseconds (ranking key)"
    )
    mean_exec_time_ms: float | None = Field(
        default=None, ge=0.0, description="Mean execution time in ms"
    )
    rows: int | None = Field(default=None, ge=0, description="Total rows returned")


class ConsolidatedIndexCandidate(BaseModel):
    """Consolidated index evaluated across the top-N workload queries."""

    model_config = ConfigDict(extra="forbid")

    index_sql: str = Field(description="CREATE INDEX DDL statement")
    table: str = Field(description="Target table name")
    columns: list[str] = Field(default_factory=list, description="Ordered index key columns")
    rationale: str = Field(default="", description="Merged rationale from proposals")
    helped_queries: list[str] = Field(
        default_factory=list, description="Query IDs whose planner cost improved"
    )
    regressed_queries: list[str] = Field(
        default_factory=list, description="Query IDs whose planner cost regressed"
    )
    hypopg_plan_changed: bool = Field(
        default=False, description="True if HypoPG confirmed a plan cost change in Postgres"
    )
    estimated_cost_before: float | None = Field(
        default=None, description="Aggregate planner cost before index"
    )
    estimated_cost_after: float | None = Field(
        default=None, description="Aggregate planner cost with index"
    )
    verified_in_sandbox: bool = Field(
        default=False, description="True if evaluated against live PostgreSQL + HypoPG"
    )


class WorkloadQueryResult(BaseModel):
    """Diagnosis outcome for a single ranked query in the workload."""

    model_config = ConfigDict(extra="forbid")

    queryid: str
    total_exec_time_ms: float
    calls: int
    original_sql: str
    verdict: str
    best_candidate: str | None = None
    proposed_indexes: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0


class WorkloadReport(BaseModel):
    """Complete Phase 9 workload diagnosis and consolidated index report."""

    model_config = ConfigDict(extra="forbid")

    total_queries_in_export: int
    top_n_analyzed: int
    total_cost_usd: float
    budget_usd: float
    query_results: list[WorkloadQueryResult] = Field(default_factory=list)
    consolidated_indexes: list[ConsolidatedIndexCandidate] = Field(default_factory=list)
    overall_hypopg_cost_reduction_pct: float = 0.0
    summary: str = ""
