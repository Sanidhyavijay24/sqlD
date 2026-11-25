"""
@file enumerator.py
@description Small-scope systematic relational dataset enumerator
@module sqldoctor/adversary/enumerator
"""

from typing import Any

from sqldoctor.adversary.constants import ValuePool, extract_value_pool
from sqldoctor.schema.models import ConstraintType, SchemaModel, TableModel


class SmallScopeEnumerator:
    """Generates small-scope relational datasets (0, 1, 2, 3 rows) using boundary value pools."""

    def __init__(self, enumeration_cap: int = 5000) -> None:
        """Initialize with permutation cap.

        Args:
            enumeration_cap: Maximum datasets generated during enumeration.
        """
        self.enumeration_cap = enumeration_cap

    def enumerate_datasets(
        self,
        schema: SchemaModel,
        query_sql: str,
    ) -> list[dict[str, list[dict[str, Any]]]]:
        """Generate a series of systematic small-scope datasets respecting schema constraints.

        Args:
            schema: Relational schema model.
            query_sql: SQL query to extract constants from.

        Returns:
            List of generated relational datasets (table_name -> list of row dicts).
        """
        pool = extract_value_pool(query_sql)
        datasets: list[dict[str, list[dict[str, Any]]]] = []

        # 1. Dataset with 0 rows across all tables (empty set check)
        empty_dataset: dict[str, list[dict[str, Any]]] = {tbl: [] for tbl in schema.tables}
        datasets.append(empty_dataset)

        # 2. Datasets with single rows per table across boundary values
        for tbl_name, tbl in schema.tables.items():
            candidate_rows = self._generate_boundary_rows(tbl, pool)
            for r in candidate_rows:
                ds: dict[str, list[dict[str, Any]]] = {t_name: [] for t_name in schema.tables}
                ds[tbl_name] = [r]
                # Populate foreign keys in parent tables if referenced
                self._satisfy_foreign_keys(ds, schema)
                datasets.append(ds)
                if len(datasets) >= self.enumeration_cap:
                    return datasets

        # 3. Two-row datasets checking duplicates, ties, and order sensitivity
        for tbl_name, tbl in schema.tables.items():
            candidate_rows = self._generate_boundary_rows(tbl, pool)
            for i in range(min(5, len(candidate_rows))):
                for j in range(i, min(10, len(candidate_rows))):
                    r1 = candidate_rows[i]
                    r2 = candidate_rows[j]
                    # Verify no primary key or unique collision
                    if not self._violates_unique(tbl, [r1, r2]):
                        two_row_ds: dict[str, list[dict[str, Any]]] = {
                            t_name: [] for t_name in schema.tables
                        }
                        two_row_ds[tbl_name] = [r1, r2]
                        self._satisfy_foreign_keys(two_row_ds, schema)
                        datasets.append(two_row_ds)
                        if len(datasets) >= self.enumeration_cap:
                            return datasets

        return datasets

    def _generate_boundary_rows(self, table: TableModel, pool: ValuePool) -> list[dict[str, Any]]:
        """Generate diverse boundary rows for a table."""
        rows: list[dict[str, Any]] = []
        cols = list(table.columns.values())
        if not cols:
            return rows

        # Generate a standard baseline row
        base_row: dict[str, Any] = {}
        for c in cols:
            vals = pool.get_values_for_type(c.data_type)
            # Pick non-null for base row
            val = next((v for v in vals if v is not None), 1)
            base_row[c.name] = val
        rows.append(base_row)

        # Generate rows varying each column individually across pool values (including NULL)
        for c in cols:
            pool_vals = pool.get_values_for_type(c.data_type)
            for v in pool_vals:
                if v is None and not c.is_nullable:
                    continue
                row_copy = dict(base_row)
                row_copy[c.name] = v
                rows.append(row_copy)

        return rows

    def _violates_unique(self, table: TableModel, rows: list[dict[str, Any]]) -> bool:
        """Check if rows violate unique or primary key constraints."""
        for con in table.constraints:
            if con.type in (ConstraintType.PRIMARY_KEY, ConstraintType.UNIQUE):
                seen: set[tuple[Any, ...]] = set()
                for r in rows:
                    key = tuple(r.get(c) for c in con.columns)
                    if None not in key:
                        if key in seen:
                            return True
                        seen.add(key)
        return False

    def _satisfy_foreign_keys(
        self, dataset: dict[str, list[dict[str, Any]]], schema: SchemaModel
    ) -> None:
        """Ensure parent tables contain referenced foreign keys."""
        for tbl_name, rows in list(dataset.items()):
            tbl = schema.tables.get(tbl_name)
            if not tbl:
                continue
            for fk in tbl.foreign_keys:
                parent_tbl = schema.tables.get(fk.foreign_table or "")
                if not parent_tbl:
                    continue
                for child_row in rows:
                    parent_row: dict[str, Any] = {}
                    for c_col, p_col in zip(fk.columns, fk.foreign_columns, strict=False):
                        val = child_row.get(c_col)
                        if val is not None:
                            parent_row[p_col] = val
                    if parent_row:
                        # Ensure non-null columns in parent have defaults
                        for p_cname, p_col_meta in parent_tbl.columns.items():
                            if p_cname not in parent_row:
                                parent_row[p_cname] = 1 if not p_col_meta.is_nullable else None
                        dataset[parent_tbl.name].append(parent_row)
