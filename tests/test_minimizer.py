"""
@file test_minimizer.py
@description Unit tests for DeltaDebuggingMinimizer
@module tests/test_minimizer
"""

from sqldoctor.adversary.minimizer import DeltaDebuggingMinimizer
from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)


def test_delta_debugging_row_minimization() -> None:
    """Verify that delta debugging removes irrelevant rows from counterexample."""
    schema = SchemaModel(
        tables={
            "items": TableModel(
                name="items",
                columns={
                    "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
                    "val": ColumnModel(name="val", data_type="integer", is_nullable=False),
                },
                constraints=[
                    ConstraintModel(name="pk", type=ConstraintType.PRIMARY_KEY, columns=["id"])
                ],
            )
        }
    )

    q_orig = "SELECT id FROM items WHERE val > 10;"
    q_cand = "SELECT id FROM items WHERE val > 5;"

    # Dataset containing 1 separating row (val=8) and 3 non-separating rows
    bloated_dataset = {
        "items": [
            {"id": 1, "val": 20},  # both return this (matches)
            {"id": 2, "val": 8},  # ONLY cand returns this (separating row!)
            {"id": 3, "val": 2},  # neither returns this
            {"id": 4, "val": 1},  # neither returns this
        ]
    }

    minimizer = DeltaDebuggingMinimizer()

    def execute_mock(
        ds: dict[str, list[dict[str, int]]], orig: str, cand: str
    ) -> tuple[list[tuple[int]], list[tuple[int]]]:
        rows = ds.get("items", [])
        orig_res = [(r["id"],) for r in rows if r["val"] > 10]
        cand_res = [(r["id"],) for r in rows if r["val"] > 5]
        return orig_res, cand_res

    minimized = minimizer.minimize(
        schema=schema,
        original_sql=q_orig,
        candidate_sql=q_cand,
        failing_dataset=bloated_dataset,
        execute_fn=execute_mock,
    )

    # Should shrink down from 4 rows to exactly the 1 minimal separating row!
    items_rows = minimized["items"]
    assert len(items_rows) == 1
    assert items_rows[0]["id"] == 2
    assert items_rows[0]["val"] == 8
