"""
@file test_pairs.py
@description Gate test: 10 hand-written query pairs judged with fixed random data
@module tests/test_pairs
"""

import pytest

from sqldoctor.compare.result import ComparisonVerdict
from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)
from sqldoctor.verifier.random_verifier import RandomVerifier


def _build_benchmark_schema() -> SchemaModel:
    """Build a rich relational schema for the 10 query pairs."""
    users_tbl = TableModel(
        name="users",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "name": ColumnModel(name="name", data_type="varchar", is_nullable=False),
            "age": ColumnModel(name="age", data_type="integer", is_nullable=False),
            "status": ColumnModel(name="status", data_type="varchar", is_nullable=False),
            "phone": ColumnModel(name="phone", data_type="varchar", is_nullable=True),
        },
        constraints=[
            ConstraintModel(name="pk_users", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    orders_tbl = TableModel(
        name="orders",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "user_id": ColumnModel(name="user_id", data_type="integer", is_nullable=False),
            "amount": ColumnModel(name="amount", data_type="numeric", is_nullable=False),
            "status": ColumnModel(name="status", data_type="varchar", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_orders", type=ConstraintType.PRIMARY_KEY, columns=["id"]),
            ConstraintModel(
                name="fk_orders_users",
                type=ConstraintType.FOREIGN_KEY,
                columns=["user_id"],
                foreign_table="users",
                foreign_columns=["id"],
            ),
        ],
    )

    products_tbl = TableModel(
        name="products",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "name": ColumnModel(name="name", data_type="varchar", is_nullable=False),
            "price": ColumnModel(name="price", data_type="numeric", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_products", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    customers_tbl = TableModel(
        name="customers",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "country": ColumnModel(name="country", data_type="varchar", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_cust", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    suppliers_tbl = TableModel(
        name="suppliers",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "country": ColumnModel(name="country", data_type="varchar", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_supp", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    return SchemaModel(
        tables={
            "users": users_tbl,
            "orders": orders_tbl,
            "products": products_tbl,
            "customers": customers_tbl,
            "suppliers": suppliers_tbl,
        }
    )


# 10 Hand-written query pairs: exactly 5 equivalent, 5 non-equivalent
TEN_QUERY_PAIRS = [
    # Pair 1: Redundant filter predicate removal (Equivalent)
    (
        "Pair 1: Redundant predicate",
        "SELECT id, name FROM users WHERE age > 18 AND age > 10;",
        "SELECT id, name FROM users WHERE age > 18;",
        ComparisonVerdict.EQUIVALENT,
    ),
    # Pair 2: Unsafe DISTINCT removal (Rejected)
    (
        "Pair 2: Unsafe DISTINCT removal",
        "SELECT DISTINCT status FROM orders;",
        "SELECT status FROM orders;",
        ComparisonVerdict.DIFFERENT,
    ),
    # Pair 3: Identity arithmetic simplification (Equivalent)
    (
        "Pair 3: Identity arithmetic",
        "SELECT id, price * 1.0 AS final_price FROM products;",
        "SELECT id, price AS final_price FROM products;",
        ComparisonVerdict.EQUIVALENT,
    ),
    # Pair 4: Outer join incorrectly turned into Inner join (Rejected)
    (
        "Pair 4: Outer to Inner join",
        "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id;",
        "SELECT u.id, o.amount FROM users u INNER JOIN orders o ON u.id = o.user_id;",
        ComparisonVerdict.DIFFERENT,
    ),
    # Pair 5: EXISTS vs IN (Equivalent)
    (
        "Pair 5: EXISTS to IN",
        (
            "SELECT u.id, u.name FROM users u "
            "WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id);"
        ),
        ("SELECT u.id, u.name FROM users u WHERE u.id IN (SELECT o.user_id FROM orders o);"),
        ComparisonVerdict.EQUIVALENT,
    ),
    # Pair 6: UNION replaced by UNION ALL with duplicate records (Rejected)
    (
        "Pair 6: UNION to UNION ALL",
        "SELECT country FROM suppliers UNION SELECT country FROM customers;",
        "SELECT country FROM suppliers UNION ALL SELECT country FROM customers;",
        ComparisonVerdict.DIFFERENT,
    ),
    # Pair 7: OR to IN list (Equivalent)
    (
        "Pair 7: OR to IN list",
        "SELECT id, status FROM orders WHERE status = 'pending' OR status = 'shipped';",
        "SELECT id, status FROM orders WHERE status IN ('pending', 'shipped');",
        ComparisonVerdict.EQUIVALENT,
    ),
    # Pair 8: COUNT(*) vs COUNT(column_with_nulls) (Rejected)
    (
        "Pair 8: COUNT(*) vs COUNT(col)",
        "SELECT COUNT(*) AS cnt FROM users;",
        "SELECT COUNT(phone) AS cnt FROM users;",
        ComparisonVerdict.DIFFERENT,
    ),
    # Pair 9: Constant propagation under WHERE (Equivalent)
    (
        "Pair 9: Constant propagation",
        "SELECT id, status FROM users WHERE status = 'active';",
        "SELECT id, 'active' AS status FROM users WHERE status = 'active';",
        ComparisonVerdict.EQUIVALENT,
    ),
    # Pair 10: Dropping a selective predicate (Rejected)
    (
        "Pair 10: Dropping predicate",
        "SELECT id, price FROM products WHERE price > 50;",
        "SELECT id, price FROM products;",
        ComparisonVerdict.DIFFERENT,
    ),
]


def test_ten_pairs_count() -> None:
    """Verify exactly 10 hand-written query pairs are present for Phase 1 gate."""
    assert len(TEN_QUERY_PAIRS) == 10


@pytest.mark.parametrize("title,orig,cand,expected_verdict", TEN_QUERY_PAIRS)
def test_handwritten_pairs_judged_correctly(
    title: str, orig: str, cand: str, expected_verdict: ComparisonVerdict
) -> None:
    """Verify each hand-written query pair is judged correctly by verifier."""
    schema = _build_benchmark_schema()
    verifier = RandomVerifier(seed=20261123, null_probability=0.35)

    result = verifier.verify(
        schema=schema,
        original_sql=orig,
        candidate_sql=cand,
        rows_per_table=12,
    )

    err_msg = (
        f"Failed on {title}: expected {expected_verdict}, "
        f"got {result.verdict}. Reason: {result.details.reason}"
    )
    assert result.verdict == expected_verdict, err_msg


def test_strict_run_to_run_determinism() -> None:
    """Verify consecutive runs with identical seed produce identical outputs."""
    schema = _build_benchmark_schema()
    title, orig, cand, expected = TEN_QUERY_PAIRS[0]

    runs: list[ComparisonVerdict] = []
    for _ in range(5):
        verifier = RandomVerifier(seed=20261123)
        res = verifier.verify(schema, orig, cand, rows_per_table=10)
        runs.append(res.verdict)

    # All runs must be completely identical
    assert all(v == expected for v in runs), f"Non-deterministic verdicts: {runs}"
