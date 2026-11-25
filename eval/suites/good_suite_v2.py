"""
@file good_suite_v2.py
@description Complete Good-Rewrite Suite v2: 30 known-equivalent SQL rewrites
@module eval/suites/good_suite_v2
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
    """Build multi-table relational schema for the 30 good rewrite cases."""
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
            "cat": ColumnModel(name="cat", data_type="varchar", is_nullable=False),
        },
        constraints=[
            ConstraintModel(name="pk_items", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    return SchemaModel(tables={"users": users_tbl, "items": items_tbl})


# 30 Known-equivalent query rewrites
GOOD_CASES_V2: list[dict[str, Any]] = [
    # 1. Redundant predicate elimination
    {
        "id": "good_01_redundant_pred",
        "category": "predicate_simplification",
        "orig": "SELECT id, age FROM users WHERE age > 18 AND age > 10;",
        "cand": "SELECT id, age FROM users WHERE age > 18;",
    },
    # 2. Commutative equality swap
    {
        "id": "good_02_eq_swap",
        "category": "commutativity",
        "orig": "SELECT id FROM users WHERE status = 'active';",
        "cand": "SELECT id FROM users WHERE 'active' = status;",
    },
    # 3. Multiplicative identity
    {
        "id": "good_03_mult_identity",
        "category": "algebraic_identity",
        "orig": "SELECT id, price * 1.0 AS p FROM items;",
        "cand": "SELECT id, price AS p FROM items;",
    },
    # 4. Constant folding
    {
        "id": "good_04_constant_folding",
        "category": "constant_folding",
        "orig": "SELECT id, val + 2 + 3 AS v FROM items;",
        "cand": "SELECT id, val + 5 AS v FROM items;",
    },
    # 5. OR to IN list
    {
        "id": "good_05_or_to_in",
        "category": "in_expansion",
        "orig": "SELECT id, status FROM users WHERE status = 'active' OR status = 'pending';",
        "cand": "SELECT id, status FROM users WHERE status IN ('active', 'pending');",
    },
    # 6. IN list permutation
    {
        "id": "good_06_in_permute",
        "category": "in_permutation",
        "orig": "SELECT id FROM users WHERE id IN (1, 2, 3);",
        "cand": "SELECT id FROM users WHERE id IN (3, 2, 1);",
    },
    # 7. Commutative addition
    {
        "id": "good_07_add_commute",
        "category": "commutativity",
        "orig": "SELECT id, price + tax AS total FROM items;",
        "cand": "SELECT id, tax + price AS total FROM items;",
    },
    # 8. Between expansion
    {
        "id": "good_08_between_expansion",
        "category": "between_expansion",
        "orig": "SELECT id, age FROM users WHERE age BETWEEN 18 AND 30;",
        "cand": "SELECT id, age FROM users WHERE age >= 18 AND age <= 30;",
    },
    # 9. Double negation removal
    {
        "id": "good_09_double_negation",
        "category": "boolean_simplification",
        "orig": "SELECT id FROM users WHERE NOT (NOT (active = 1));",
        "cand": "SELECT id FROM users WHERE active = 1;",
    },
    # 10. Inlining trivial CTE
    {
        "id": "good_10_cte_inlining",
        "category": "cte_inlining",
        "orig": "WITH u AS (SELECT id, username FROM users) SELECT id, username FROM u;",
        "cand": "SELECT id, username FROM users;",
    },
    # 11. Associative multiplication
    {
        "id": "good_11_mult_associative",
        "category": "algebraic_identity",
        "orig": "SELECT id, (val * 2) * 3 AS total FROM items;",
        "cand": "SELECT id, val * 6 AS total FROM items;",
    },
    # 12. Redundant TRUE conjunct elimination
    {
        "id": "good_12_true_conjunct",
        "category": "boolean_simplification",
        "orig": "SELECT id FROM users WHERE age > 20 AND 1 = 1;",
        "cand": "SELECT id FROM users WHERE age > 20;",
    },
    # 13. Identity CASE statement
    {
        "id": "good_13_case_identity",
        "category": "case_simplification",
        "orig": "SELECT id, CASE WHEN 1 = 1 THEN status ELSE 'other' END FROM users;",
        "cand": "SELECT id, status FROM users;",
    },
    # 14. Subtraction by zero
    {
        "id": "good_14_sub_zero",
        "category": "algebraic_identity",
        "orig": "SELECT id, val - 0 AS v FROM items;",
        "cand": "SELECT id, val AS v FROM items;",
    },
    # 15. Explicit inner join table commutativity
    {
        "id": "good_15_join_commute",
        "category": "join_commutativity",
        "orig": "SELECT u.id, i.price FROM users u JOIN items i ON u.id = i.id;",
        "cand": "SELECT u.id, i.price FROM items i JOIN users u ON u.id = i.id;",
    },
    # 16. De Morgan's Law: NOT (a OR b) <=> NOT a AND NOT b
    {
        "id": "good_16_de_morgan_and",
        "category": "boolean_simplification",
        "orig": "SELECT id FROM users WHERE NOT (age < 18 OR active = 0);",
        "cand": "SELECT id FROM users WHERE age >= 18 AND active <> 0;",
    },
    # 17. Elimination of FALSE disjunct
    {
        "id": "good_17_false_disjunct",
        "category": "boolean_simplification",
        "orig": "SELECT id FROM items WHERE price > 100 OR 1 = 0;",
        "cand": "SELECT id FROM items WHERE price > 100;",
    },
    # 18. Unnesting trivial single-table subquery
    {
        "id": "good_18_subquery_unnest",
        "category": "subquery_unnesting",
        "orig": "SELECT sub.id, sub.price FROM (SELECT id, price FROM items) sub;",
        "cand": "SELECT id, price FROM items;",
    },
    # 19. Converting comma join to explicit INNER JOIN
    {
        "id": "good_19_comma_to_inner_join",
        "category": "join_syntax",
        "orig": "SELECT u.id, i.price FROM users u, items i WHERE u.id = i.id;",
        "cand": "SELECT u.id, i.price FROM users u INNER JOIN items i ON u.id = i.id;",
    },
    # 20. Commutative multiplication
    {
        "id": "good_20_mult_commute",
        "category": "commutativity",
        "orig": "SELECT id, price * tax AS tax_amt FROM items;",
        "cand": "SELECT id, tax * price AS tax_amt FROM items;",
    },
    # 21. Factoring common conjunct
    {
        "id": "good_21_factor_conjunct",
        "category": "boolean_factoring",
        "orig": "SELECT id FROM users WHERE (active = 1 AND age > 20) OR (active = 1 AND age < 15);",
        "cand": "SELECT id FROM users WHERE active = 1 AND (age > 20 OR age < 15);",
    },
    # 22. COALESCE on NOT NULL column is identity
    {
        "id": "good_22_coalesce_not_null",
        "category": "coalesce_identity",
        "orig": "SELECT id, COALESCE(username, 'anonymous') FROM users;",
        "cand": "SELECT id, username FROM users;",
    },
    # 23. IN subquery to EXISTS on NOT NULL primary key
    {
        "id": "good_23_in_to_exists",
        "category": "subquery_exists",
        "orig": "SELECT u.id FROM users u WHERE u.id IN (SELECT i.id FROM items i);",
        "cand": "SELECT u.id FROM users u WHERE EXISTS (SELECT 1 FROM items i WHERE i.id = u.id);",
    },
    # 24. Redundant parentheses elimination
    {
        "id": "good_24_redundant_parens",
        "category": "ast_simplification",
        "orig": "SELECT id FROM items WHERE (((val + 10))) > 50;",
        "cand": "SELECT id FROM items WHERE val + 10 > 50;",
    },
    # 25. Reversing BETWEEN comparison operands
    {
        "id": "good_25_between_order",
        "category": "between_expansion",
        "orig": "SELECT id FROM users WHERE 18 <= age AND age <= 65;",
        "cand": "SELECT id FROM users WHERE age BETWEEN 18 AND 65;",
    },
    # 26. Redundant DISTINCT on UNIQUE PRIMARY KEY
    {
        "id": "good_26_distinct_on_pk",
        "category": "distinct_removal",
        "orig": "SELECT DISTINCT id FROM users;",
        "cand": "SELECT id FROM users;",
    },
    # 27. Repeated addition to multiplication
    {
        "id": "good_27_addition_to_mult",
        "category": "algebraic_identity",
        "orig": "SELECT id, val + val AS v FROM items;",
        "cand": "SELECT id, val * 2 AS v FROM items;",
    },
    # 28. Division by 1.0 identity
    {
        "id": "good_28_div_one_identity",
        "category": "algebraic_identity",
        "orig": "SELECT id, price / 1.0 AS p FROM items;",
        "cand": "SELECT id, price AS p FROM items;",
    },
    # 29. Disjoint range UNION to UNION ALL
    {
        "id": "good_29_disjoint_union_all",
        "category": "union_all_conversion",
        "orig": "SELECT id FROM users WHERE age < 30 UNION SELECT id FROM users WHERE age >= 30;",
        "cand": "SELECT id FROM users WHERE age < 30 UNION ALL SELECT id FROM users WHERE age >= 30;",
    },
    # 30. Associative addition
    {
        "id": "good_30_add_associative",
        "category": "algebraic_identity",
        "orig": "SELECT id, (val + 10) + 20 AS v FROM items;",
        "cand": "SELECT id, val + 30 AS v FROM items;",
    },
]
