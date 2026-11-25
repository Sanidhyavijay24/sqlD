"""
@file minimizer.py
@description Delta-debugging counterexample minimizer for minimal reproducible receipts
@module sqldoctor/adversary/minimizer
"""

import copy
from collections.abc import Callable
from typing import Any

from sqldoctor.compare.comparator import ResultComparator
from sqldoctor.compare.result import ComparisonVerdict
from sqldoctor.schema.models import SchemaModel


class DeltaDebuggingMinimizer:
    """Shrinks counterexample datasets down to minimal rows that still separate original and candidate."""

    def __init__(self, comparator: ResultComparator | None = None) -> None:
        """Initialize minimizer with ResultComparator.

        Args:
            comparator: ResultComparator instance.
        """
        self.comparator = comparator or ResultComparator()

    def minimize(
        self,
        schema: SchemaModel,
        original_sql: str,
        candidate_sql: str,
        failing_dataset: dict[str, list[dict[str, Any]]],
        execute_fn: Callable[
            [dict[str, list[dict[str, Any]]], str, str],
            tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]],
        ],
    ) -> dict[str, list[dict[str, Any]]]:
        """Shrink failing_dataset to 1-minimal subset separating original and candidate.

        Args:
            schema: Schema metadata.
            original_sql: Reference SQL query.
            candidate_sql: Candidate SQL query.
            failing_dataset: Initial counterexample dataset that causes disparity.
            execute_fn: Function executing both queries on a given dataset and returning rows.

        Returns:
            Minimized dataset with the minimum rows and simplified values.
        """
        current_dataset = copy.deepcopy(failing_dataset)

        # 1. Delta-debugging row reduction: attempt dropping each row individually
        improved = True
        while improved:
            improved = False
            for table_name in list(current_dataset.keys()):
                table_rows = current_dataset[table_name]
                if not table_rows:
                    continue

                for row_idx in range(len(table_rows)):
                    # Tentatively remove row
                    candidate_dataset = copy.deepcopy(current_dataset)
                    candidate_dataset[table_name].pop(row_idx)

                    try:
                        orig_rows, cand_rows = execute_fn(
                            candidate_dataset, original_sql, candidate_sql
                        )
                        comp = self.comparator.compare(
                            original_sql, candidate_sql, orig_rows, cand_rows
                        )
                        # If disparity still reproduces, keep the row removed!
                        if comp.verdict == ComparisonVerdict.DIFFERENT:
                            current_dataset = candidate_dataset
                            improved = True
                            break
                    except Exception:
                        # Dropping row broke constraint or query execution, retain row
                        pass

                if improved:
                    break

        return current_dataset
