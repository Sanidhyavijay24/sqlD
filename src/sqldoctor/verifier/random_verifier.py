"""
@file random_verifier.py
@description Baseline verifier comparing queries on fixed random datasets
@module sqldoctor/verifier/random_verifier
"""

import sqlite3
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field

from sqldoctor.compare.comparator import ResultComparator
from sqldoctor.compare.result import ComparisonDetails, ComparisonVerdict
from sqldoctor.datagen.generator import SeededDataGenerator
from sqldoctor.schema.models import SchemaModel


class RandomVerifierResult(BaseModel):
    """Output verdict and details from random data verification."""

    model_config = ConfigDict(extra="forbid")

    verdict: ComparisonVerdict = Field(description="Resulting comparison verdict")
    is_equivalent: bool = Field(description="Whether queries returned matching results")
    seed: int = Field(description="Deterministic PRNG seed used for data generation")
    rows_generated_per_table: int = Field(description="Row count per table in test dataset")
    details: ComparisonDetails = Field(description="Detailed comparison metrics")


class RandomVerifier:
    """Fixed-random-data verifier serving as Phase 1 engine and Phase 5 baseline."""

    def __init__(
        self,
        seed: int = 20261123,
        comparator: ResultComparator | None = None,
        null_probability: float = 0.25,
    ) -> None:
        """Initialize with seed and comparator.

        Args:
            seed: Deterministic PRNG seed.
            comparator: ResultComparator instance (or default if None).
            null_probability: Rate of NULL value generation.
        """
        self.seed = seed
        self.comparator = comparator or ResultComparator()
        self.generator = SeededDataGenerator(seed=seed, null_probability=null_probability)

    def verify(
        self,
        schema: SchemaModel,
        original_sql: str,
        candidate_sql: str,
        rows_per_table: int = 15,
        connection_uri: str | None = None,
    ) -> RandomVerifierResult:
        """Run verification of original vs candidate query on a fixed random dataset.

        Args:
            schema: Schema metadata model.
            original_sql: Reference SQL query.
            candidate_sql: Rewrite candidate SQL query.
            rows_per_table: Scale of generated dataset per table.
            connection_uri: Optional PostgreSQL URI (if None, runs in-memory).

        Returns:
            RandomVerifierResult with verdict, details, and seed.
        """
        # 1. Deterministically synthesize data
        dataset = self.generator.generate_schema_data(schema=schema, rows_per_table=rows_per_table)

        orig_rows: list[tuple[Any, ...]]
        cand_rows: list[tuple[Any, ...]]

        if connection_uri:
            orig_rows, cand_rows = self._execute_postgres(
                connection_uri=connection_uri,
                schema=schema,
                dataset=dataset,
                original_sql=original_sql,
                candidate_sql=candidate_sql,
            )
        else:
            orig_rows, cand_rows = self._execute_in_memory(
                schema=schema,
                dataset=dataset,
                original_sql=original_sql,
                candidate_sql=candidate_sql,
            )

        # 2. Compare outputs with ResultComparator
        comp_details = self.comparator.compare(
            original_sql=original_sql,
            candidate_sql=candidate_sql,
            original_rows=orig_rows,
            candidate_rows=cand_rows,
        )

        return RandomVerifierResult(
            verdict=comp_details.verdict,
            is_equivalent=comp_details.is_equivalent,
            seed=self.seed,
            rows_generated_per_table=rows_per_table,
            details=comp_details,
        )

    def _execute_in_memory(
        self,
        schema: SchemaModel,
        dataset: dict[str, list[dict[str, Any]]],
        original_sql: str,
        candidate_sql: str,
    ) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        """Execute queries in an isolated in-memory database."""
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()

        try:
            # Create tables and insert data
            for table_name, rows in dataset.items():
                table = schema.tables[table_name]
                cols = list(table.columns.keys())
                col_defs = ", ".join([f'"{c}" TEXT' for c in cols])
                cur.execute(f'CREATE TABLE "{table_name}" ({col_defs});')

                if rows:
                    cols_str = ", ".join([f'"{c}"' for c in cols])
                    placeholders = ", ".join(["?"] * len(cols))
                    insert_sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'
                    row_tuples = [
                        tuple(None if r.get(c) is None else str(r.get(c)) for c in cols)
                        for r in rows
                    ]
                    cur.executemany(insert_sql, row_tuples)

            conn.commit()

            cur.execute(original_sql)
            orig_rows = cur.fetchall()

            cur.execute(candidate_sql)
            cand_rows = cur.fetchall()

            return orig_rows, cand_rows
        finally:
            conn.close()

    def _execute_postgres(
        self,
        connection_uri: str,
        schema: SchemaModel,
        dataset: dict[str, list[dict[str, Any]]],
        original_sql: str,
        candidate_sql: str,
    ) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        """Execute queries in an isolated PostgreSQL temporary schema."""
        temp_schema = f"sqld_rand_{self.seed}"

        with psycopg.connect(connection_uri) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE;")
                cur.execute(f"CREATE SCHEMA {temp_schema};")
                cur.execute(f"SET search_path TO {temp_schema}, public;")

                # Populate generated rows
                for table_name, rows in dataset.items():
                    table = schema.tables[table_name]
                    cols = list(table.columns.keys())
                    if rows:
                        col_list = ", ".join([f'"{c}"' for c in cols])
                        placeholders = ", ".join(["%s"] * len(cols))
                        insert_sql = (
                            f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders});'
                        )
                        batch = [tuple(r.get(c) for c in cols) for r in rows]
                        cur.executemany(insert_sql, batch)

                cur.execute(original_sql)
                orig_rows = cur.fetchall() if cur.description else []

                cur.execute(candidate_sql)
                cand_rows = cur.fetchall() if cur.description else []

                cur.execute(f"DROP SCHEMA IF EXISTS {temp_schema} CASCADE;")
                conn.commit()

        return orig_rows, cand_rows
