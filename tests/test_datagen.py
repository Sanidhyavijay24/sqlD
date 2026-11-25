"""
@file test_datagen.py
@description Unit tests for constraint-aware seeded synthetic data generator
@module tests/test_datagen
"""

from typing import Any

from sqldoctor.datagen.generator import SeededDataGenerator
from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)


def _build_test_schema() -> SchemaModel:
    """Build relational schema with PK, FK, NOT NULL, and UNIQUE constraints."""
    customers_cols = {
        "customer_id": ColumnModel(name="customer_id", data_type="integer", is_nullable=False),
        "email": ColumnModel(name="email", data_type="varchar", is_nullable=False),
        "nickname": ColumnModel(name="nickname", data_type="varchar", is_nullable=True),
    }
    customers_constraints = [
        ConstraintModel(name="pk_cust", type=ConstraintType.PRIMARY_KEY, columns=["customer_id"]),
        ConstraintModel(name="uq_email", type=ConstraintType.UNIQUE, columns=["email"]),
    ]
    customers_tbl = TableModel(
        name="customers", columns=customers_cols, constraints=customers_constraints
    )

    orders_cols = {
        "order_id": ColumnModel(name="order_id", data_type="bigint", is_nullable=False),
        "customer_id": ColumnModel(name="customer_id", data_type="integer", is_nullable=False),
        "order_total": ColumnModel(name="order_total", data_type="numeric", is_nullable=False),
    }
    orders_constraints = [
        ConstraintModel(name="pk_orders", type=ConstraintType.PRIMARY_KEY, columns=["order_id"]),
        ConstraintModel(
            name="fk_cust",
            type=ConstraintType.FOREIGN_KEY,
            columns=["customer_id"],
            foreign_table="customers",
            foreign_columns=["customer_id"],
        ),
    ]
    orders_tbl = TableModel(name="orders", columns=orders_cols, constraints=orders_constraints)

    return SchemaModel(tables={"customers": customers_tbl, "orders": orders_tbl})


def test_generator_determinism() -> None:
    """Verify that identical seeds produce bit-for-bit identical relational data."""
    schema = _build_test_schema()
    gen1 = SeededDataGenerator(seed=42)
    gen2 = SeededDataGenerator(seed=42)
    gen3 = SeededDataGenerator(seed=999)

    data1 = gen1.generate_schema_data(schema, rows_per_table=5)
    data2 = gen2.generate_schema_data(schema, rows_per_table=5)
    data3 = gen3.generate_schema_data(schema, rows_per_table=5)

    assert data1 == data2, "Identical seeds must produce identical data"
    assert data1 != data3, "Different seeds must produce different data"


def test_not_null_and_unique_constraints() -> None:
    """Verify NOT NULL columns never have None and UNIQUE has no duplicates."""
    schema = _build_test_schema()
    gen = SeededDataGenerator(seed=12345, null_probability=0.5)
    data = gen.generate_schema_data(schema, rows_per_table=10)

    customers = data["customers"]
    cust_ids = [c["customer_id"] for c in customers]
    emails = [c["email"] for c in customers]

    # No NULL in NOT NULL columns
    assert all(cid is not None for cid in cust_ids)
    assert all(em is not None for em in emails)

    # No duplicates in unique columns
    assert len(cust_ids) == len(set(cust_ids))
    assert len(emails) == len(set(emails))


def test_foreign_key_referential_integrity() -> None:
    """Verify generated child table rows strictly reference parent rows."""
    schema = _build_test_schema()
    gen = SeededDataGenerator(seed=777)
    data = gen.generate_schema_data(schema, rows_per_table=8)

    customers = data["customers"]
    orders = data["orders"]

    parent_ids = {c["customer_id"] for c in customers}
    assert len(parent_ids) > 0

    for order in orders:
        assert order["customer_id"] in parent_ids, (
            f"Orphan FK: {order['customer_id']} not in {parent_ids}"
        )


def test_to_copy_format() -> None:
    """Verify conversion to PostgreSQL COPY TSV syntax with \\N for NULL."""
    table = TableModel(
        name="test",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "note": ColumnModel(name="note", data_type="text", is_nullable=True),
        },
    )
    rows: list[dict[str, Any]] = [
        {"id": 1, "note": "hello\tworld"},
        {"id": 2, "note": None},
    ]

    gen = SeededDataGenerator(seed=1)
    copy_str = gen.to_copy_format(table, rows)

    lines = copy_str.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "1\thello\\tworld"
    assert lines[1] == "2\t\\N"
