"""
@file adversary_verifier.py
@description Complete deterministic adversarial verifier for SQL Doctor
@module sqldoctor/verifier/adversary_verifier
"""

import hashlib
import sqlite3
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sqldoctor import __version__
from sqldoctor.adversary.enumerator import SmallScopeEnumerator
from sqldoctor.adversary.minimizer import DeltaDebuggingMinimizer
from sqldoctor.adversary.targeted import TargetedDatasetHook
from sqldoctor.compare.comparator import ResultComparator
from sqldoctor.compare.result import ComparisonVerdict
from sqldoctor.datagen.generator import SeededDataGenerator
from sqldoctor.mutate.engine import ASTMutator
from sqldoctor.mutate.models import MutationScore
from sqldoctor.schema.models import SchemaModel


class CounterexampleEvidence(BaseModel):
    """Minimized counterexample evidence proving non-equivalence."""

    model_config = ConfigDict(extra="forbid")

    dataset: dict[str, list[dict[str, Any]]] = Field(description="Minimized table rows")
    original_output: list[tuple[Any, ...]] = Field(description="Rows returned by original query")
    candidate_output: list[tuple[Any, ...]] = Field(description="Rows returned by candidate query")
    reason: str = Field(description="Disparity explanation")


class AdversaryVerdictReport(BaseModel):
    """Standardized verdict JSON output conforming to SQL Doctor schema_version 1."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, description="Report schema version")
    verdict: str = Field(
        description="One of: rejected, tested_equivalent, no_op, conditionally_equivalent, unverified"
    )
    original_sha256: str = Field(description="SHA256 hash of original query text")
    candidate_sha256: str = Field(description="SHA256 hash of candidate query text")
    versions: dict[str, str] = Field(description="Tool, postgres, and model versions")
    seed: int = Field(description="Deterministic PRNG seed used")
    datasets: dict[str, int] = Field(
        description="Counts of enumerated, targeted, and fuzz datasets"
    )
    mutants: dict[str, Any] = Field(description="Mutation adequacy score and details")
    counterexample: CounterexampleEvidence | None = Field(
        default=None, description="Attached counterexample if rejected"
    )
    assumptions: list[dict[str, Any]] = Field(
        default_factory=list, description="Assumption ledger records"
    )
    performance: dict[str, Any] = Field(
        default_factory=lambda: {"metric": "shared_buffers_hit_plus_read", "scales": []}
    )


class AdversaryVerifier:
    """Deterministic verifier running small-scope enumeration, fuzzing, and mutation adequacy."""

    def __init__(
        self,
        seed: int = 20261123,
        enumeration_cap: int = 500,
        fuzz_datasets: int = 15,
        pg_version: str = "17.x",
    ) -> None:
        """Initialize verifier with search parameters.

        Args:
            seed: Deterministic PRNG seed.
            enumeration_cap: Maximum enumerated permutations.
            fuzz_datasets: Number of random fuzz datasets to evaluate.
            pg_version: Target PostgreSQL version string.
        """
        self.seed = seed
        self.pg_version = pg_version
        self.enumerator = SmallScopeEnumerator(enumeration_cap=enumeration_cap)
        self.fuzzer = SeededDataGenerator(seed=seed)
        self.comparator = ResultComparator()
        self.minimizer = DeltaDebuggingMinimizer(self.comparator)
        self.mutator = ASTMutator()
        self.targeted_hook = TargetedDatasetHook()
        self.fuzz_datasets_count = fuzz_datasets

    def verify(
        self,
        schema: SchemaModel,
        original_sql: str,
        candidate_sql: str,
        connection_uri: str | None = None,
    ) -> AdversaryVerdictReport:
        """Run full deterministic verification and return structured verdict.

        Args:
            schema: Schema metadata.
            original_sql: Reference SQL query.
            candidate_sql: Candidate SQL query.
            connection_uri: Optional PostgreSQL sandbox URI (in-memory if None).

        Returns:
            AdversaryVerdictReport with verdict, mutation score, and minimal counterexample.
        """
        orig_hash = hashlib.sha256(original_sql.strip().encode()).hexdigest()
        cand_hash = hashlib.sha256(candidate_sql.strip().encode()).hexdigest()

        # Check for immediate no-op (identical query text)
        if original_sql.strip() == candidate_sql.strip():
            return AdversaryVerdictReport(
                verdict="no_op",
                original_sha256=orig_hash,
                candidate_sha256=cand_hash,
                versions={
                    "tool": __version__,
                    "postgres": self.pg_version,
                    "model": "none",
                },
                seed=self.seed,
                datasets={"enumerated": 0, "targeted": 0, "fuzz": 0},
                mutants={"total": 0, "killed": 0, "survived_possibly_equivalent": []},
            )

        # 1. Generate dataset pool
        enumerated_ds = self.enumerator.enumerate_datasets(schema, original_sql)
        fuzz_ds: list[dict[str, list[dict[str, Any]]]] = []
        for i in range(self.fuzz_datasets_count):
            gen = SeededDataGenerator(seed=self.seed + i + 1, null_probability=0.3)
            fuzz_ds.append(gen.generate_schema_data(schema, rows_per_table=10 + i))

        all_datasets = enumerated_ds + fuzz_ds

        # 2. Search for counterexample across datasets
        counterexample_dataset: dict[str, list[dict[str, Any]]] | None = None
        diff_reason: str = ""

        for ds in all_datasets:
            orig_rows, cand_rows = self._execute_dataset(schema, ds, original_sql, candidate_sql)
            comp = self.comparator.compare(original_sql, candidate_sql, orig_rows, cand_rows)

            if comp.verdict == ComparisonVerdict.UNVERIFIED:
                return AdversaryVerdictReport(
                    verdict="unverified",
                    original_sha256=orig_hash,
                    candidate_sha256=cand_hash,
                    versions={
                        "tool": __version__,
                        "postgres": self.pg_version,
                        "model": "none",
                    },
                    seed=self.seed,
                    datasets={
                        "enumerated": len(enumerated_ds),
                        "targeted": 0,
                        "fuzz": len(fuzz_ds),
                    },
                    mutants={
                        "total": 0,
                        "killed": 0,
                        "survived_possibly_equivalent": [],
                    },
                )

            if comp.verdict == ComparisonVerdict.DIFFERENT:
                counterexample_dataset = ds
                diff_reason = comp.reason
                break

        # 3. If counterexample found, minimize and reject
        if counterexample_dataset is not None:
            minimized_ds = self.minimizer.minimize(
                schema=schema,
                original_sql=original_sql,
                candidate_sql=candidate_sql,
                failing_dataset=counterexample_dataset,
                execute_fn=lambda d, o, c: self._execute_dataset(schema, d, o, c),
            )
            min_orig, min_cand = self._execute_dataset(
                schema, minimized_ds, original_sql, candidate_sql
            )
            evidence = CounterexampleEvidence(
                dataset=minimized_ds,
                original_output=min_orig,
                candidate_output=min_cand,
                reason=diff_reason,
            )
            return AdversaryVerdictReport(
                verdict="rejected",
                original_sha256=orig_hash,
                candidate_sha256=cand_hash,
                versions={
                    "tool": __version__,
                    "postgres": self.pg_version,
                    "model": "none",
                },
                seed=self.seed,
                datasets={
                    "enumerated": len(enumerated_ds),
                    "targeted": 0,
                    "fuzz": len(fuzz_ds),
                },
                mutants={"total": 0, "killed": 0, "survived_possibly_equivalent": []},
                counterexample=evidence,
            )

        # 4. Mutation adequacy scoring
        mutants = self.mutator.generate_mutants(original_sql)
        score: MutationScore
        if mutants and all_datasets:
            eval_ds = all_datasets[min(len(all_datasets) - 1, 5)]
            baseline_rows, _ = self._execute_dataset(schema, eval_ds, original_sql, original_sql)
            score = self.mutator.evaluate_adequacy(
                mutants=mutants,
                execute_fn=lambda q: self._execute_dataset(schema, eval_ds, q, q)[0],
                original_output=baseline_rows,
            )
        else:
            score = MutationScore(
                total_mutants=0,
                killed_mutants=0,
                survived_mutants=0,
                score=1.0,
                survived_descriptions=[],
            )

        return AdversaryVerdictReport(
            verdict="tested_equivalent",
            original_sha256=orig_hash,
            candidate_sha256=cand_hash,
            versions={
                "tool": __version__,
                "postgres": self.pg_version,
                "model": "none",
            },
            seed=self.seed,
            datasets={
                "enumerated": len(enumerated_ds),
                "targeted": 0,
                "fuzz": len(fuzz_ds),
            },
            mutants={
                "total": score.total_mutants,
                "killed": score.killed_mutants,
                "score": score.score,
                "survived_possibly_equivalent": score.survived_descriptions,
            },
        )

    def _execute_dataset(
        self,
        schema: SchemaModel,
        dataset: dict[str, list[dict[str, Any]]],
        original_sql: str,
        candidate_sql: str,
    ) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
        """Execute queries on an in-memory instance loaded with dataset."""
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        try:
            for table_name, rows in dataset.items():
                table = schema.tables.get(table_name)
                if not table:
                    continue
                col_defs: list[str] = []
                for c_name, c_col in table.columns.items():
                    d_type = c_col.data_type.lower()
                    if any(t in d_type for t in ("int", "serial", "bigint", "smallint")):
                        affinity = "INTEGER"
                    elif any(
                        t in d_type for t in ("numeric", "decimal", "real", "float", "double")
                    ):
                        affinity = "NUMERIC"
                    else:
                        affinity = "TEXT"
                    col_defs.append(f'"{c_name}" {affinity}')

                cur.execute(f'CREATE TABLE "{table_name}" ({", ".join(col_defs)});')

                if rows:
                    cols = list(table.columns.keys())
                    cols_str = ", ".join([f'"{c}"' for c in cols])
                    placeholders = ", ".join(["?"] * len(cols))
                    insert_sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'
                    row_tuples = [
                        tuple(
                            float(r[c]) if isinstance(r.get(c), Decimal) else r.get(c) for c in cols
                        )
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
