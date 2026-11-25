"""
@file writer.py
@description Standalone self-contained SQL receipt writer conforming to SQL Doctor receipt specification
@module sqldoctor/receipt/writer
"""

import datetime
from pathlib import Path

from sqldoctor import __version__
from sqldoctor.schema.models import SchemaModel
from sqldoctor.verifier.adversary_verifier import AdversaryVerdictReport


class ReceiptWriter:
    """Generates self-contained, standalone .sql receipts replayable in plain psql."""

    def __init__(self, pg_version: str = "17.x") -> None:
        self.pg_version = pg_version

    def generate_receipt_sql(
        self,
        original_sql: str,
        candidate_sql: str,
        verdict_report: AdversaryVerdictReport,
        schema: SchemaModel | None = None,
        explanation: str = "",
    ) -> str:
        """Construct the complete self-contained SQL receipt text.

        Args:
            original_sql: Reference SQL query.
            candidate_sql: Candidate SQL query.
            verdict_report: Verdict report from adversary verifier.
            schema: Schema metadata.
            explanation: Diagnostic explanation or rationale.

        Returns:
            Formatted self-contained SQL receipt string.
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        verdict = verdict_report.verdict.upper()

        lines: list[str] = [
            "-- " + "=" * 76,
            "-- SQL DOCTOR VERIFICATION RECEIPT",
            f"-- Verdict: {verdict}",
            f"-- Tool Version: {__version__} | PostgreSQL Target: {self.pg_version}",
            f"-- Seed: {verdict_report.seed} | Generated: {now}",
        ]
        if explanation:
            lines.append(f"-- Rationale: {explanation.strip().replace('\n', ' ')}")
        lines.extend(
            [
                "-- " + "=" * 76,
                "",
                "-- 1. Schema Definition (DDL)",
                "BEGIN;",
            ]
        )

        # 1. DDL Statements
        if schema:
            for tname, tmodel in schema.tables.items():
                col_defs = []
                for c in tmodel.columns.values():
                    c_str = f"    {c.name} {c.data_type}"
                    if not c.is_nullable:
                        c_str += " NOT NULL"
                    col_defs.append(c_str)
                for con in tmodel.constraints:
                    if con.type.value == "PRIMARY KEY":
                        col_defs.append(
                            f"    CONSTRAINT {con.name} PRIMARY KEY ({', '.join(con.columns)})"
                        )
                lines.append(f"DROP TABLE IF EXISTS {tname} CASCADE;")
                lines.append(f"CREATE TABLE {tname} (")
                lines.append(",\n".join(col_defs))
                lines.append(");")
                lines.append("")

        # 2. Minimal Counterexample Dataset (or empty tables if tested_equivalent)
        lines.append("-- 2. Test Dataset (Minimal Counterexample / Verification Seed)")
        if verdict_report.counterexample and verdict_report.counterexample.dataset:
            ce_data = verdict_report.counterexample.dataset
            for tname, rows in ce_data.items():
                if not rows:
                    continue
                cols = list(rows[0].keys())
                for r in rows:
                    vals = []
                    for col_name in cols:
                        val = r.get(col_name)
                        if val is None:
                            vals.append("NULL")
                        elif isinstance(val, (int, float)):
                            vals.append(str(val))
                        elif isinstance(val, bool):
                            vals.append("TRUE" if val else "FALSE")
                        else:
                            clean_str = str(val).replace("'", "''")
                            vals.append(f"'{clean_str}'")
                    lines.append(
                        f"INSERT INTO {tname} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
                    )
        lines.append("")

        # 3. Query Definitions (CTEs / Views)
        clean_orig = original_sql.strip().rstrip(";")
        clean_cand = candidate_sql.strip().rstrip(";")

        lines.extend(
            [
                "-- 3. Query Equivalence Comparison",
                "-- Run both queries over the test dataset and compare results via multiset bag equality (EXCEPT ALL).",
                "WITH original_query AS (",
                f"    {clean_orig}",
                "),",
                "candidate_query AS (",
                f"    {clean_cand}",
                "),",
                "disparities AS (",
                "    -- Rows produced by original but missing from candidate",
                "    (SELECT 'ORIGINAL_ONLY' AS source, o.* FROM (SELECT * FROM original_query EXCEPT ALL SELECT * FROM candidate_query) o)",
                "    UNION ALL",
                "    -- Rows produced by candidate but missing from original",
                "    (SELECT 'CANDIDATE_ONLY' AS source, c.* FROM (SELECT * FROM candidate_query EXCEPT ALL SELECT * FROM original_query) c)",
                ")",
                "SELECT * FROM disparities;",
                "",
                "ROLLBACK;",
                "",
                "-- " + "=" * 76,
                "-- EXPECTED OUTPUT:",
            ]
        )

        if verdict in ("TESTED_EQUIVALENT", "NO_OP"):
            lines.extend(
                [
                    "-- 0 rows returned.",
                    "-- (Queries produce identical multiset bag results across all test permutations).",
                ]
            )
        else:
            reason = (
                verdict_report.counterexample.reason
                if verdict_report.counterexample
                else "Result disparity"
            )
            lines.extend(
                [
                    f"-- Disparity rows returned proving non-equivalence: {reason}",
                ]
            )
            if verdict_report.counterexample:
                lines.append(f"-- Original output: {verdict_report.counterexample.original_output}")
                lines.append(
                    f"-- Candidate output: {verdict_report.counterexample.candidate_output}"
                )

        lines.extend(
            [
                "-- " + "=" * 76,
                "",
            ]
        )

        return "\n".join(lines)

    def write_receipt(
        self,
        output_path: Path | str,
        original_sql: str,
        candidate_sql: str,
        verdict_report: AdversaryVerdictReport,
        schema: SchemaModel | None = None,
        explanation: str = "",
    ) -> Path:
        """Write self-contained receipt to disk.

        Args:
            output_path: Destination path for receipt.sql.
            original_sql: Reference SQL.
            candidate_sql: Candidate rewrite.
            verdict_report: Adversary report.
            schema: Optional schema model.
            explanation: Diagnostic explanation.

        Returns:
            Resolved Path object of created receipt.
        """
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_receipt_sql(
            original_sql=original_sql,
            candidate_sql=candidate_sql,
            verdict_report=verdict_report,
            schema=schema,
            explanation=explanation,
        )
        p.write_text(content, encoding="utf-8")
        return p
