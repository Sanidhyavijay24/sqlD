"""
@file replay.py
@description Replay engine for SQL Doctor receipts: re-executes receipt.sql and verifies verdict reproduction
@module sqldoctor/receipt/replay
"""

import re
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sqldoctor.compare.comparator import ResultComparator
from sqldoctor.sandbox.client import SandboxClient


class ReplayResult(BaseModel):
    """Result of replaying a self-contained SQL Doctor receipt."""

    model_config = ConfigDict(extra="forbid")

    receipt_path: str
    recorded_verdict: str
    observed_verdict: str
    matches: bool
    disparity_count: int = 0
    disparity_rows: list[tuple[Any, ...]] = Field(default_factory=list)
    message: str = ""


class ReceiptReplayer:
    """Executes a standalone receipt.sql and confirms verdict reproducibility."""

    def __init__(self, db_client: SandboxClient | None = None) -> None:
        self.db_client = db_client
        self.comparator = ResultComparator()

    def parse_header_verdict(self, receipt_text: str) -> str:
        """Extract the recorded verdict from receipt header comments."""
        match = re.search(r"^--\s*Verdict:\s*([A-Z_]+)", receipt_text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return "UNKNOWN"

    def replay_in_sqlite(
        self, receipt_path: Path | str, receipt_text: str, recorded_verdict: str
    ) -> ReplayResult:
        """Replay receipt in an in-memory SQLite database when no PostgreSQL container is available."""
        # Extract DDL, INSERTs, and queries
        lines = receipt_text.splitlines()

        orig_query_sql = ""
        cand_query_sql = ""

        # Extract CTE queries
        orig_match = re.search(
            r"WITH\s+original_query\s+AS\s*\(\s*(.*?)\s*\),",
            receipt_text,
            re.DOTALL | re.IGNORECASE,
        )
        cand_match = re.search(
            r"candidate_query\s+AS\s*\(\s*(.*?)\s*\),\s*disparities",
            receipt_text,
            re.DOTALL | re.IGNORECASE,
        )

        if orig_match and cand_match:
            orig_query_sql = orig_match.group(1).strip()
            cand_query_sql = cand_match.group(1).strip()

        # Extract table setup
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        current_stmt = []
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("--") or not trimmed:
                continue
            if trimmed in ("BEGIN;", "ROLLBACK;", "COMMIT;"):
                continue
            if "DROP TABLE" in trimmed.upper() and "CASCADE" in trimmed.upper():
                trimmed = re.sub(r"\s+CASCADE", "", trimmed, flags=re.IGNORECASE)

            # SQLite type adjustments
            trimmed = re.sub(r"\bBOOLEAN\b", "INTEGER", trimmed, flags=re.IGNORECASE)
            trimmed = re.sub(r"\bNUMERIC\b", "REAL", trimmed, flags=re.IGNORECASE)
            trimmed = re.sub(r"\bTRUE\b", "1", trimmed)
            trimmed = re.sub(r"\bFALSE\b", "0", trimmed)

            current_stmt.append(trimmed)
            if trimmed.endswith(";"):
                stmt = " ".join(current_stmt)
                current_stmt = []
                if "SELECT * FROM disparities" in stmt:
                    break
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass

        conn.commit()

        # Execute queries and compare
        observed_verdict = "UNKNOWN"
        disparity_rows: list[tuple[Any, ...]] = []

        try:
            # Query comparison via comparator
            orig_rows = cursor.execute(orig_query_sql).fetchall()
            cand_rows = cursor.execute(cand_query_sql).fetchall()
            details = self.comparator.compare(orig_query_sql, cand_query_sql, orig_rows, cand_rows)
            if details.is_equivalent:
                observed_verdict = "TESTED_EQUIVALENT"
            else:
                observed_verdict = "REJECTED"
                disparity_rows = [("ORIGINAL_ONLY", r) for r in orig_rows if r not in cand_rows] + [
                    ("CANDIDATE_ONLY", r) for r in cand_rows if r not in orig_rows
                ]
        except Exception as e:
            conn.close()
            return ReplayResult(
                receipt_path=str(receipt_path),
                recorded_verdict=recorded_verdict,
                observed_verdict="ERROR",
                matches=False,
                message=f"Replay execution error: {e}",
            )

        conn.close()

        matches = (observed_verdict.upper() == recorded_verdict.upper()) or (
            observed_verdict.upper() == "TESTED_EQUIVALENT" and recorded_verdict.upper() == "NO_OP"
        )
        msg = (
            f"Receipt successfully verified: {observed_verdict} reproduces recorded verdict."
            if matches
            else f"Verdict disparity! Recorded: {recorded_verdict}, Observed: {observed_verdict}."
        )

        return ReplayResult(
            receipt_path=str(receipt_path),
            recorded_verdict=recorded_verdict,
            observed_verdict=observed_verdict,
            matches=matches,
            disparity_count=len(disparity_rows),
            disparity_rows=disparity_rows,
            message=msg,
        )

    def replay(self, receipt_path: Path | str) -> ReplayResult:
        """Replay receipt file and verify that the recorded verdict reproduces.

        Args:
            receipt_path: Path to the receipt.sql file.

        Returns:
            ReplayResult object.
        """
        p = Path(receipt_path)
        if not p.is_file():
            raise FileNotFoundError(f"Receipt file not found: {receipt_path}")

        receipt_text = p.read_text(encoding="utf-8")
        recorded_verdict = self.parse_header_verdict(receipt_text)

        if self.db_client:
            try:
                rows = self.db_client.execute_query(receipt_text)
                disparity_count = len(rows)
                observed_verdict = "TESTED_EQUIVALENT" if disparity_count == 0 else "REJECTED"
                matches = (observed_verdict.upper() == recorded_verdict.upper()) or (
                    observed_verdict.upper() == "TESTED_EQUIVALENT"
                    and recorded_verdict.upper() == "NO_OP"
                )
                msg = (
                    f"PostgreSQL replay confirmed: {observed_verdict}"
                    if matches
                    else f"PostgreSQL replay mismatch: expected {recorded_verdict}, observed {observed_verdict}"
                )
                return ReplayResult(
                    receipt_path=str(receipt_path),
                    recorded_verdict=recorded_verdict,
                    observed_verdict=observed_verdict,
                    matches=matches,
                    disparity_count=disparity_count,
                    disparity_rows=rows,
                    message=msg,
                )
            except Exception:
                # Fallback to in-memory replay
                pass

        return self.replay_in_sqlite(receipt_path, receipt_text, recorded_verdict)
