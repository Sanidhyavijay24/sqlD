"""
@file __init__.py
@description Phase 9 Workload Mode: pg_stat_statements ranking, index consolidation, and HypoPG verification
@module sqldoctor/workload
"""

from sqldoctor.workload.models import (
    ConsolidatedIndexCandidate,
    StatStatementEntry,
    WorkloadQueryResult,
    WorkloadReport,
)
from sqldoctor.workload.parser import parse_pg_stat_statements

__all__ = [
    "ConsolidatedIndexCandidate",
    "StatStatementEntry",
    "WorkloadQueryResult",
    "WorkloadReport",
    "parse_pg_stat_statements",
]
