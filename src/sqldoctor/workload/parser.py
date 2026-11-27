"""
@file parser.py
@description Parser and ranker for PostgreSQL pg_stat_statements JSON and CSV exports
@module sqldoctor/workload/parser
"""

import csv
import io
import json
from pathlib import Path
from typing import Any

from sqldoctor.workload.models import StatStatementEntry


def _extract_total_time_ms(row: dict[str, Any]) -> float:
    """Extract total execution time supporting PG13+ (total_exec_time) and older (total_time)."""
    for key in ("total_exec_time_ms", "total_exec_time", "total_time"):
        if key in row and row[key] is not None and str(row[key]).strip() != "":
            return float(row[key])
    return 0.0


def _extract_mean_time_ms(row: dict[str, Any]) -> float | None:
    """Extract optional mean execution time."""
    for key in ("mean_exec_time_ms", "mean_exec_time", "mean_time"):
        if key in row and row[key] is not None and str(row[key]).strip() != "":
            return float(row[key])
    return None


def _is_optimizable_query(sql: str) -> bool:
    """Filter out transaction control and pg_catalog/pg_stat_statements introspection queries."""
    upper = sql.strip().upper()
    if not upper:
        return False
    if "PG_STAT_STATEMENTS" in upper:
        return False
    return upper.startswith("SELECT") or upper.startswith("WITH")


def parse_pg_stat_statements(source: str | Path) -> list[StatStatementEntry]:
    """Parse a pg_stat_statements JSON or CSV export and return entries ranked by total_exec_time_ms.

    Args:
        source: Path to a .json or .csv export file, or raw JSON/CSV content string.

    Returns:
        List of StatStatementEntry sorted descending by total_exec_time_ms.
    """
    raw_text: str
    path = Path(source) if isinstance(source, Path) or "\n" not in str(source) else None
    if path is not None and path.is_file():
        raw_text = path.read_text(encoding="utf-8")
    else:
        raw_text = str(source)

    stripped = raw_text.strip()
    if not stripped:
        return []

    raw_rows: list[dict[str, Any]]
    if stripped.startswith("[") or stripped.startswith("{"):
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            extracted = parsed.get("rows") or parsed.get("statements") or [parsed]
            raw_rows = list(extracted) if isinstance(extracted, list) else [parsed]
        elif isinstance(parsed, list):
            raw_rows = parsed
        else:
            raise ValueError("Unsupported JSON format for pg_stat_statements export.")
    else:
        reader = csv.DictReader(io.StringIO(stripped))
        raw_rows = list(reader)

    entries: list[StatStatementEntry] = []
    for idx, row in enumerate(raw_rows):
        query = str(row.get("query", "")).strip()
        if not _is_optimizable_query(query):
            continue
        queryid = str(row.get("queryid") or f"q_{idx + 1}")
        calls_raw = row.get("calls", 1)
        calls = int(float(str(calls_raw))) if calls_raw not in (None, "") else 1
        rows_raw = row.get("rows")
        rows_val = int(float(str(rows_raw))) if rows_raw not in (None, "") else None

        entries.append(
            StatStatementEntry(
                queryid=queryid,
                query=query,
                calls=max(calls, 0),
                total_exec_time_ms=_extract_total_time_ms(row),
                mean_exec_time_ms=_extract_mean_time_ms(row),
                rows=rows_val,
            )
        )

    entries.sort(key=lambda e: e.total_exec_time_ms, reverse=True)
    return entries
