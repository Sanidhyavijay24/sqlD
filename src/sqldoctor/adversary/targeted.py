"""
@file targeted.py
@description Hook for LLM-targeted datasets with fixture support for testing
@module sqldoctor/adversary/targeted
"""

from typing import Any

from sqldoctor.schema.models import SchemaModel


class TargetedDatasetHook:
    """Generates or loads targeted datasets aimed at separating surviving mutants."""

    def __init__(self, fixtures: dict[str, dict[str, list[dict[str, Any]]]] | None = None) -> None:
        """Initialize with optional offline fixtures.

        Args:
            fixtures: Map of query_key -> relational dataset fixture.
        """
        self.fixtures = fixtures or {}

    def get_targeted_dataset(
        self,
        schema: SchemaModel,
        original_sql: str,
        mutant_sql: str,
    ) -> dict[str, list[dict[str, Any]]] | None:
        """Fetch targeted separating dataset from fixtures or LLM target constructor.

        Args:
            schema: SchemaModel metadata.
            original_sql: Reference query.
            mutant_sql: Mutated query that survived.

        Returns:
            Dataset dict if targeted fixture found, else None.
        """
        # Lookup in pre-configured fixtures
        for key, ds in self.fixtures.items():
            if key in original_sql or key in mutant_sql:
                return ds
        return None
