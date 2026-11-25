"""
@file good_suite_v1.py
@description Good-rewrite suite v1: 15 known-equivalent rewrites
@module eval/suites/good_suite_v1
"""

from typing import Any

from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)


def get_good_suite_schema() -> SchemaModel:
    """Build multi-table schema for the 15 good rewrite cases."""
    users_tbl = TableModel(
        name="users",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "username": ColumnModel(name="username", data_type="varchar", is_nullable=False),
            "age": ColumnModel(name="age", data_type="integer", is_nullable=False),
            "status": ColumnModel(name="status", data_type="varchar", is_nullable=False),
            "active": ColumnModel(name="active", data_type="integer", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_users", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    items_tbl = TableModel(
        name="items",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "price": ColumnModel(name="price", data_type="numeric", is_nullable=False),
            "tax": ColumnModel(name="tax", data_type="numeric", is_nullable=False),
            "val": ColumnModel(name="val", data_type="integer", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_items", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    return SchemaModel(tables={"users": users_tbl, "items": items_tbl})


# 15 Known-equivalent query rewrites
GOOD_CASES_V1: list[dict[str, Any]] = [
    # Good 1: Redundant predicate elimination
    {
        "id": "good_01_redundant_pred",
        "category": "predicate_simplification",
        "orig": "SELECT id, age FROM users WHERE age > 18 AND age > 10;",
        "cand": "SELECT id, age FROM users WHERE age > 18;",
    },
    # Good 2: Commutative equality swap
    {
        "id": "good_02_eq_swap",
        "category": "commutativity",
        "orig": "SELECT id FROM users WHERE status = 'active';",
        "cand": "SELECT id FROM users WHERE 'active' = status;",
    },
    # Good 3: Multiplicative identity
    {
        "id": "good_03_mult_identity",
        "category": "algebraic_identity",
        "orig": "SELECT id, price * 1.0 AS p FROM items;",
        "cand": "SELECT id, price AS p FROM items;",
    },
    # Good 4: Constant folding
    {
        "id": "good_04_constant_folding",
        "category": "constant_folding",
        "orig": "SELECT id, val + 2 + 3 AS v FROM items;",
        "cand": "SELECT id, val + 5 AS v FROM items;",
    },
    # Good 5: OR to IN list
    {
        "id": "good_05_or_to_in",
        "category": "in_expansion",
        "orig": ("SELECT id, status FROM users WHERE status = 'active' OR status = 'pending';"),
        "cand": "SELECT id, status FROM users WHERE status IN ('active', 'pending');",
    },
    # Good 6: IN list permutation
    {
        "id": "good_06_in_permute",
        "category": "in_permutation",
        "orig": "SELECT id FROM users WHERE id IN (1, 2, 3);",
        "cand": "SELECT id FROM users WHERE id IN (3, 2, 1);",
    },
    # Good 7: Commutative addition
    {
        "id": "good_07_add_commute",
        "category": "commutativity",
        "orig": "SELECT id, price + tax AS total FROM items;",
        "cand": "SELECT id, tax + price AS total FROM items;",
    },
    # Good 8: Between expansion
    {
        "id": "good_08_between_expansion",
        "category": "between_expansion",
        "orig": "SELECT id, age FROM users WHERE age BETWEEN 18 AND 30;",
        "cand": "SELECT id, age FROM users WHERE age >= 18 AND age <= 30;",
    },
    # Good 9: Double negation removal
    {
        "id": "good_09_double_negation",
        "category": "boolean_simplification",
        "orig": "SELECT id FROM users WHERE NOT (NOT (active = 1));",
        "cand": "SELECT id FROM users WHERE active = 1;",
    },
    # Good 10: Inlining trivial CTE
    {
        "id": "good_10_cte_inlining",
        "category": "cte_inlining",
        "orig": ("WITH u AS (SELECT id, username FROM users) SELECT id, username FROM u;"),
        "cand": "SELECT id, username FROM users;",
    },
    # Good 11: Associative multiplication
    {
        "id": "good_11_mult_associative",
        "category": "algebraic_identity",
        "orig": "SELECT id, (val * 2) * 3 AS total FROM items;",
        "cand": "SELECT id, val * 6 AS total FROM items;",
    },
    # Good 12: Redundant TRUE conjunct elimination
    {
        "id": "good_12_true_conjunct",
        "category": "boolean_simplification",
        "orig": "SELECT id FROM users WHERE age > 20 AND 1 = 1;",
        "cand": "SELECT id FROM users WHERE age > 20;",
    },
    # Good 13: Identity CASE statement
    {
        "id": "good_13_case_identity",
        "category": "case_simplification",
        "orig": "SELECT id, CASE WHEN 1 = 1 THEN status ELSE 'other' END FROM users;",
        "cand": "SELECT id, status FROM users;",
    },
    # Good 14: Subtraction by zero
    {
        "id": "good_14_sub_zero",
        "category": "algebraic_identity",
        "orig": "SELECT id, val - 0 AS v FROM items;",
        "cand": "SELECT id, val AS v FROM items;",
    },
    # Good 15: Explicit inner join table commutativity
    {
        "id": "good_15_join_commute",
        "category": "join_commutativity",
        "orig": "SELECT u.id, i.price FROM users u JOIN items i ON u.id = i.id;",
        "cand": "SELECT u.id, i.price FROM items i JOIN users u ON u.id = i.id;",
    },
]
