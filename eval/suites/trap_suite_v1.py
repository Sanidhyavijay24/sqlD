"""
@file trap_suite_v1.py
@description Trap suite v1: 25 known-wrong rewrites that SQL Doctor must reject
@module eval/suites/trap_suite_v1
"""

from typing import Any

from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)


def get_trap_suite_schema() -> SchemaModel:
    """Build multi-table schema for the 25 trap cases."""
    users_tbl = TableModel(
        name="users",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "username": ColumnModel(name="username", data_type="varchar", is_nullable=False),
            "age": ColumnModel(name="age", data_type="integer", is_nullable=False),
            "active": ColumnModel(name="active", data_type="integer", is_nullable=False),
            "phone": ColumnModel(name="phone", data_type="varchar", is_nullable=True),
            "col": ColumnModel(name="col", data_type="integer", is_nullable=True),
            "email": ColumnModel(name="email", data_type="varchar", is_nullable=True),
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
            "customer_id": ColumnModel(name="customer_id", data_type="integer", is_nullable=True),
            "amount": ColumnModel(name="amount", data_type="numeric", is_nullable=True),
            "status": ColumnModel(name="status", data_type="varchar", is_nullable=True),
        },
        constraints=[
            ConstraintModel(name="pk_orders", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    order_items_tbl = TableModel(
        name="order_items",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "order_id": ColumnModel(name="order_id", data_type="integer", is_nullable=False),
            "price": ColumnModel(name="price", data_type="numeric", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_oi", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    banned_tbl = TableModel(
        name="banned",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=True),
        },
    )

    items_tbl = TableModel(
        name="items",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "category": ColumnModel(name="category", data_type="varchar", is_nullable=True),
            "status": ColumnModel(name="status", data_type="varchar", is_nullable=True),
            "serial_no": ColumnModel(name="serial_no", data_type="varchar", is_nullable=True),
            "val": ColumnModel(name="val", data_type="integer", is_nullable=True),
            "score": ColumnModel(name="score", data_type="integer", is_nullable=True),
            "active": ColumnModel(name="active", data_type="integer", is_nullable=True),
            "priority": ColumnModel(name="priority", data_type="integer", is_nullable=True),
            "flagged": ColumnModel(name="flagged", data_type="integer", is_nullable=True),
        },
        constraints=[
            ConstraintModel(name="pk_items", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    t1_tbl = TableModel(
        name="t1",
        columns={"val": ColumnModel(name="val", data_type="integer", is_nullable=True)},
    )
    t2_tbl = TableModel(
        name="t2",
        columns={"val": ColumnModel(name="val", data_type="integer", is_nullable=True)},
    )

    return SchemaModel(
        tables={
            "users": users_tbl,
            "orders": orders_tbl,
            "order_items": order_items_tbl,
            "banned": banned_tbl,
            "items": items_tbl,
            "t1": t1_tbl,
            "t2": t2_tbl,
        }
    )


# 25 Known-wrong query rewrite traps across major bug categories
TRAP_CASES_V1: list[dict[str, Any]] = [
    # Trap 1: NOT IN vs NOT EXISTS with NULLs
    {
        "id": "trap_01_not_in_nulls",
        "category": "not_in_null",
        "orig": "SELECT id FROM orders WHERE customer_id NOT IN (SELECT id FROM banned WHERE id IS NOT NULL);",
        "cand": "SELECT id FROM orders WHERE customer_id NOT IN (SELECT id FROM banned);",
    },
    # Trap 2: UNION to UNION ALL
    {
        "id": "trap_02_union_to_all",
        "category": "union_all",
        "orig": "SELECT status FROM orders UNION SELECT category FROM items;",
        "cand": "SELECT status FROM orders UNION ALL SELECT category FROM items;",
    },
    # Trap 3: Dropping DISTINCT
    {
        "id": "trap_03_drop_distinct",
        "category": "distinct",
        "orig": "SELECT DISTINCT category FROM items;",
        "cand": "SELECT category FROM items;",
    },
    # Trap 4: Adding DISTINCT that changes row count
    {
        "id": "trap_04_add_distinct_name",
        "category": "distinct",
        "orig": "SELECT id, category FROM items;",
        "cand": "SELECT DISTINCT category FROM items;",
    },
    # Trap 5: Outer join to Inner join
    {
        "id": "trap_05_outer_to_inner",
        "category": "outer_join",
        "orig": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id;",
        "cand": "SELECT u.id, o.amount FROM users u JOIN orders o ON u.id = o.user_id;",
    },
    # Trap 6: Predicate pushdown into LEFT JOIN
    {
        "id": "trap_06_pushdown_outer",
        "category": "outer_join",
        "orig": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id WHERE o.amount > 100 OR o.amount IS NULL;",
        "cand": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id AND o.amount > 100;",
    },
    # Trap 7: Ties under LIMIT without total ORDER BY
    {
        "id": "trap_07_limit_ties",
        "category": "limit_ties",
        "orig": "SELECT id, score FROM items ORDER BY score DESC LIMIT 1;",
        "cand": "SELECT id, score FROM items ORDER BY score ASC LIMIT 1;",
    },
    # Trap 8: COUNT(*) vs COUNT(col)
    {
        "id": "trap_08_count_col_nulls",
        "category": "aggregate_null",
        "orig": "SELECT COUNT(*) AS c FROM items;",
        "cand": "SELECT COUNT(serial_no) AS c FROM items;",
    },
    # Trap 9: HAVING vs WHERE filter
    {
        "id": "trap_09_having_vs_where",
        "category": "having_where",
        "orig": "SELECT category, SUM(val) FROM items WHERE val > 10 GROUP BY category;",
        "cand": "SELECT category, SUM(val) FROM items GROUP BY category HAVING SUM(val) > 10;",
    },
    # Trap 10: Correlated subquery to JOIN with duplicate keys
    {
        "id": "trap_10_subquery_to_join_dups",
        "category": "duplicate_join",
        "orig": "SELECT u.id, u.username FROM users u WHERE (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) > 0;",
        "cand": "SELECT u.id, u.username FROM users u JOIN orders o ON o.user_id = u.id;",
    },
    # Trap 11: Incomplete NOT IN expansion with NULLs
    {
        "id": "trap_11_not_in_or",
        "category": "null_logic",
        "orig": "SELECT id FROM items WHERE status NOT IN ('open', 'closed');",
        "cand": "SELECT id FROM items WHERE status <> 'open' OR status <> 'closed';",
    },
    # Trap 12: Empty group with COUNT
    {
        "id": "trap_12_empty_group_count",
        "category": "empty_group",
        "orig": "SELECT COUNT(id) FROM users WHERE 1 = 0;",
        "cand": "SELECT COUNT(id) FROM users WHERE 1 = 0 GROUP BY id;",
    },
    # Trap 13: Off-by-one boundary
    {
        "id": "trap_13_off_by_one",
        "category": "boundary",
        "orig": "SELECT id FROM users WHERE age > 21;",
        "cand": "SELECT id FROM users WHERE age >= 21;",
    },
    # Trap 14: Integer division vs float
    {
        "id": "trap_14_int_div",
        "category": "type_cast",
        "orig": "SELECT id, score / 2.0 AS s FROM items;",
        "cand": "SELECT id, score / 2 AS s FROM items;",
    },
    # Trap 15: Negation with NULLs
    {
        "id": "trap_15_negation_nulls",
        "category": "null_logic",
        "orig": "SELECT id FROM users WHERE col <= 10 OR col IS NULL;",
        "cand": "SELECT id FROM users WHERE col <= 10;",
    },
    # Trap 16: LEFT JOIN ON condition moved to WHERE
    {
        "id": "trap_16_left_join_where",
        "category": "outer_join",
        "orig": "SELECT u.id FROM users u LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'active';",
        "cand": "SELECT u.id FROM users u LEFT JOIN orders o ON u.id = o.user_id WHERE o.status = 'active';",
    },
    # Trap 17: AVG vs SUM/COUNT with NULLs
    {
        "id": "trap_17_avg_nulls",
        "category": "aggregate_null",
        "orig": "SELECT AVG(score) FROM items;",
        "cand": "SELECT SUM(score) * 1.0 / COUNT(*) FROM items;",
    },
    # Trap 18: CASE missing ELSE branch
    {
        "id": "trap_18_case_no_else",
        "category": "case_logic",
        "orig": "SELECT CASE WHEN val > 0 THEN 'pos' ELSE 'other' END FROM items;",
        "cand": "SELECT CASE WHEN val > 0 THEN 'pos' END FROM items;",
    },
    # Trap 19: COALESCE argument ordering
    {
        "id": "trap_19_coalesce_order",
        "category": "coalesce",
        "orig": "SELECT COALESCE(email, phone, 'none') FROM users;",
        "cand": "SELECT COALESCE(phone, email, 'none') FROM users;",
    },
    # Trap 20: LIKE vs exact equality
    {
        "id": "trap_20_like_vs_eq",
        "category": "string_matching",
        "orig": "SELECT id FROM users WHERE username = 'admin%';",
        "cand": "SELECT id FROM users WHERE username LIKE 'admin%';",
    },
    # Trap 21: MAX() vs LIMIT 1 on empty table
    {
        "id": "trap_21_max_vs_limit",
        "category": "empty_table",
        "orig": "SELECT MAX(score) FROM items;",
        "cand": "SELECT score FROM items ORDER BY score DESC LIMIT 1;",
    },
    # Trap 22: Duplicate multiplication via child table join
    {
        "id": "trap_22_subquery_in_vs_join",
        "category": "duplicate_join",
        "orig": "SELECT id FROM orders WHERE id IN (SELECT order_id FROM order_items);",
        "cand": "SELECT o.id FROM orders o JOIN order_items oi ON o.id = oi.order_id;",
    },
    # Trap 23: Default window frame running sum vs whole group sum
    {
        "id": "trap_23_window_frame_order",
        "category": "window_frame",
        "orig": "SELECT id, SUM(val) OVER (PARTITION BY category) FROM items;",
        "cand": "SELECT id, SUM(val) OVER (PARTITION BY category ORDER BY id) FROM items;",
    },
    # Trap 24: Unintended sign change in arithmetic
    {
        "id": "trap_24_sign_flip",
        "category": "arithmetic",
        "orig": "SELECT id, -val FROM items;",
        "cand": "SELECT id, val FROM items;",
    },
    # Trap 25: Operator precedence bug AND vs OR
    {
        "id": "trap_25_operator_precedence",
        "category": "boolean_precedence",
        "orig": "SELECT id FROM items WHERE active = 1 AND (priority = 1 OR flagged = 1);",
        "cand": "SELECT id FROM items WHERE active = 1 AND priority = 1 OR flagged = 1;",
    },
]
