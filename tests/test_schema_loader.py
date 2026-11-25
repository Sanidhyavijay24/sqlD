"""
@file test_schema_loader.py
@description Unit tests for SchemaModel and catalog loader extraction logic
@module tests/test_schema_loader
"""

from unittest.mock import MagicMock

from sqldoctor.schema.loader import SchemaLoader
from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)


def test_schema_model_helpers() -> None:
    """Test helper properties on TableModel and SchemaModel."""
    cols = {
        "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
        "user_id": ColumnModel(name="user_id", data_type="integer", is_nullable=False),
        "code": ColumnModel(name="code", data_type="text", is_nullable=True),
    }

    constraints = [
        ConstraintModel(name="pk_table", type=ConstraintType.PRIMARY_KEY, columns=["id"]),
        ConstraintModel(
            name="fk_user",
            type=ConstraintType.FOREIGN_KEY,
            columns=["user_id"],
            foreign_table="users",
            foreign_columns=["id"],
        ),
        ConstraintModel(name="uq_code", type=ConstraintType.UNIQUE, columns=["code"]),
        ConstraintModel(
            name="chk_code_len",
            type=ConstraintType.CHECK,
            columns=["code"],
            check_clause="length(code) > 2",
        ),
    ]

    table = TableModel(name="sample_table", columns=cols, constraints=constraints)
    schema = SchemaModel(tables={"sample_table": table})

    # Assert helper property lookups
    assert table.primary_key_columns == ["id"]
    assert len(table.foreign_keys) == 1
    assert table.foreign_keys[0].foreign_table == "users"
    assert len(table.unique_constraints) == 1
    assert len(table.check_constraints) == 1

    # Case-insensitive schema retrieval
    assert schema.get_table("SAMPLE_TABLE") is not None
    assert schema.get_table("non_existent") is None


def test_schema_loader_mocked(mocker: MagicMock) -> None:
    """Verify catalog extraction logic executes expected system catalog queries."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate catalog responses:
    # 1. table names
    # 2. columns
    # 3. constraints
    # 4. indexes
    mock_cursor.fetchall.side_effect = [
        [("orders",)],  # table_names
        [  # columns
            ("order_id", "bigint", "NO", None, None, 64, 0),
            ("total", "numeric", "YES", "0.0", None, 12, 2),
        ],
        [  # constraints
            ("orders_pkey", "p", "PRIMARY KEY (order_id)", ["order_id"], None, None),
        ],
        [  # indexes
            (
                "orders_pkey",
                True,
                True,
                "btree",
                "CREATE UNIQUE INDEX ...",
                ["order_id"],
            ),
        ],
    ]

    mocker.patch("psycopg.connect", return_value=mock_conn)

    loader = SchemaLoader("postgresql://postgres:postgres@localhost:54329/postgres")
    schema = loader.load_schema()

    assert "orders" in schema.tables
    table = schema.tables["orders"]
    assert table.name == "orders"
    assert "order_id" in table.columns
    assert not table.columns["order_id"].is_nullable
    assert table.primary_key_columns == ["order_id"]
    assert len(table.indexes) == 1
    assert table.indexes[0].is_primary
