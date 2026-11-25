"""
@file generator.py
@description Deterministic constraint-aware seeded synthetic data generator
@module sqldoctor/datagen/generator
"""

import datetime
import random
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqldoctor.schema.models import ColumnModel, ConstraintType, SchemaModel, TableModel


class DataGenError(Exception):
    """Raised when data generation violates schema constraints."""


class SeededDataGenerator:
    """Generates synthetic relational data respecting constraints with fixed seeds."""

    def __init__(self, seed: int = 20261123, null_probability: float = 0.2) -> None:
        """Initialize generator with fixed seed.

        Args:
            seed: Integer seed guaranteeing reproducible random values.
            null_probability: Probability of generating NULL for nullable columns.
        """
        self.seed = seed
        self.null_probability = null_probability
        self.rng = random.Random(seed)

    def generate_schema_data(
        self,
        schema: SchemaModel,
        rows_per_table: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate relational rows for all tables in topological dependency order.

        Args:
            schema: Validated SchemaModel containing tables and constraints.
            rows_per_table: Target row count per table.

        Returns:
            Dictionary mapping table name to list of row dictionaries.
        """
        # Reset RNG to ensure strict determinism per generation call with this seed
        self.rng = random.Random(self.seed)

        ordered_tables = self._topological_sort(schema)
        generated_data: dict[str, list[dict[str, Any]]] = {}

        for table in ordered_tables:
            table_rows = self._generate_table_rows(
                table=table,
                row_count=rows_per_table,
                existing_data=generated_data,
            )
            generated_data[table.name] = table_rows

        return generated_data

    def _topological_sort(self, schema: SchemaModel) -> list[TableModel]:
        """Sort tables so parent tables appear before dependent child tables."""
        in_degree: dict[str, int] = defaultdict(int)
        adj: dict[str, list[str]] = defaultdict(list)

        table_map = {tbl.name.lower(): tbl for tbl in schema.tables.values()}

        for tbl_name in table_map:
            in_degree[tbl_name] = 0

        for tbl in schema.tables.values():
            child_name = tbl.name.lower()
            for fk in tbl.foreign_keys:
                if fk.foreign_table:
                    parent_name = fk.foreign_table.lower()
                    if parent_name in table_map and parent_name != child_name:
                        adj[parent_name].append(child_name)
                        in_degree[child_name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        sorted_names: list[str] = []

        while queue:
            # Deterministic pop using sorted queue order
            queue.sort()
            curr = queue.pop(0)
            sorted_names.append(curr)

            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # In case of cycles, append any remaining tables deterministically
        for tbl_name in sorted(table_map.keys()):
            if tbl_name not in sorted_names:
                sorted_names.append(tbl_name)

        return [table_map[name] for name in sorted_names]

    def _generate_table_rows(
        self,
        table: TableModel,
        row_count: int,
        existing_data: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Generate compliant rows for a single table."""
        rows: list[dict[str, Any]] = []
        unique_trackers: dict[str, set[Any]] = defaultdict(set)
        composite_unique_trackers: list[tuple[list[str], set[tuple[Any, ...]]]] = []

        # Find single-column and multi-column unique constraints (including PK)
        for con in table.constraints:
            if con.type in (ConstraintType.PRIMARY_KEY, ConstraintType.UNIQUE):
                if len(con.columns) == 1:
                    unique_trackers[con.columns[0]] = set()
                elif len(con.columns) > 1:
                    composite_unique_trackers.append((con.columns, set()))

        for row_idx in range(row_count):
            row_dict: dict[str, Any] = {}
            max_retries = 100

            for _ in range(max_retries):
                candidate_row: dict[str, Any] = {}

                # 1. First assign foreign key values from referenced parent tables
                for fk in table.foreign_keys:
                    parent_table_name = fk.foreign_table
                    if (
                        parent_table_name
                        and parent_table_name in existing_data
                        and existing_data[parent_table_name]
                    ):
                        parent_row = self.rng.choice(existing_data[parent_table_name])
                        for child_col, parent_col in zip(
                            fk.columns, fk.foreign_columns, strict=False
                        ):
                            candidate_row[child_col] = parent_row.get(parent_col)

                # 2. Fill remaining columns
                for col_name, col in table.columns.items():
                    if col_name in candidate_row:
                        continue

                    is_pk = col_name in table.primary_key_columns
                    is_unique = col_name in unique_trackers

                    val = self._generate_column_value(
                        col=col,
                        is_unique=is_unique or is_pk,
                        row_index=row_idx,
                        used_values=unique_trackers.get(col_name),
                    )
                    candidate_row[col_name] = val

                # 3. Check uniqueness constraints
                violates_unique = False
                for col_name, used_set in unique_trackers.items():
                    val = candidate_row.get(col_name)
                    if val is not None and val in used_set:
                        violates_unique = True
                        break

                for cols, comp_set in composite_unique_trackers:
                    comp_key = tuple(candidate_row.get(c) for c in cols)
                    if None not in comp_key and comp_key in comp_set:
                        violates_unique = True
                        break

                if not violates_unique:
                    row_dict = candidate_row
                    # Record unique entries
                    for col_name, used_set in unique_trackers.items():
                        if candidate_row.get(col_name) is not None:
                            used_set.add(candidate_row[col_name])
                    for cols, comp_set in composite_unique_trackers:
                        comp_key = tuple(candidate_row.get(c) for c in cols)
                        if None not in comp_key:
                            comp_set.add(comp_key)
                    break

            if row_dict:
                rows.append(row_dict)

        return rows

    def _generate_column_value(
        self,
        col: ColumnModel,
        is_unique: bool,
        row_index: int,
        used_values: set[Any] | None,
    ) -> Any:
        """Generate scalar value for a column respecting type and constraints."""
        # Check nullable flag
        if col.is_nullable and not is_unique and self.rng.random() < self.null_probability:
            return None

        d_type = col.data_type.lower()

        # Integer types
        if any(
            t in d_type for t in ("int", "integer", "bigint", "smallint", "serial", "bigserial")
        ):
            if is_unique:
                base = row_index + 1
                while used_values is not None and base in used_values:
                    base += 1
                return base
            return self.rng.choice([1, 2, 3, 5, 10, 50, 100])

        # Floating / Numeric / Decimal
        if any(t in d_type for t in ("numeric", "decimal", "real", "double", "float")):
            val = round(self.rng.uniform(1.0, 500.0), 2)
            if is_unique and used_values is not None:
                val += float(row_index)
            return Decimal(str(val))

        # Boolean
        if "bool" in d_type:
            return self.rng.choice([True, False])

        # Date / Timestamp
        if any(t in d_type for t in ("timestamp", "date", "time")):
            base_date = datetime.date(2026, 1, 1)
            offset_days = row_index * 7 + self.rng.randint(0, 30)
            target_date = base_date + datetime.timedelta(days=offset_days)
            if "date" in d_type and "timestamp" not in d_type:
                return target_date.isoformat()
            return f"{target_date.isoformat()}T12:00:00Z"

        # Character / Text
        if any(t in d_type for t in ("char", "varchar", "text")):
            max_len = col.character_maximum_length or 50
            if is_unique:
                text_val = f"val_{col.name}_{row_index}_{self.rng.randint(100, 999)}"
            else:
                words = ["alpha", "beta", "gamma", "delta", "epsilon", "omega"]
                text_val = self.rng.choice(words)
            return text_val[:max_len]

        # Default fallback
        return f"item_{row_index}"

    def to_copy_format(self, table: TableModel, rows: list[dict[str, Any]]) -> str:
        """Convert rows into PostgreSQL COPY TSV format with \\N representing NULL.

        Args:
            table: Target table metadata.
            rows: Generated row dictionaries.

        Returns:
            TSV string ready for COPY ... FROM STDIN.
        """
        col_names = list(table.columns.keys())
        lines: list[str] = []

        for row in rows:
            line_vals: list[str] = []
            for col_name in col_names:
                v = row.get(col_name)
                if v is None:
                    line_vals.append(r"\N")
                elif isinstance(v, bool):
                    line_vals.append("TRUE" if v else "FALSE")
                else:
                    # Escape tab, newline, backslash
                    s = str(v).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
                    line_vals.append(s)
            lines.append("\t".join(line_vals))

        return "\n".join(lines) + ("\n" if lines else "")
