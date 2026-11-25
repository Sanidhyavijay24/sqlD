"""
@file trap_suite_v2.py
@description Complete Trap Suite v2: 50 comprehensive known-wrong SQL rewrites across all bug categories
@module eval/suites/trap_suite_v2
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
    """Build multi-table relational schema for the 50 trap cases."""
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
            "x": ColumnModel(name="x", data_type="integer", is_nullable=True),
            "y": ColumnModel(name="y", data_type="integer", is_nullable=True),
        },
        constraints=[
            ConstraintModel(name="pk_items", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )

    t1_tbl = TableModel(
        name="t1",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "val": ColumnModel(name="val", data_type="integer", is_nullable=True),
            "txt": ColumnModel(name="txt", data_type="varchar", is_nullable=True),
        },
        constraints=[
            ConstraintModel(name="pk_t1", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
    )
    t2_tbl = TableModel(
        name="t2",
        columns={
            "id": ColumnModel(name="id", data_type="integer", is_nullable=False),
            "val": ColumnModel(name="val", data_type="integer", is_nullable=True),
            "txt": ColumnModel(name="txt", data_type="varchar", is_nullable=True),
        },
        constraints=[
            ConstraintModel(name="pk_t2", type=ConstraintType.PRIMARY_KEY, columns=["id"])
        ],
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


# 50 Known-wrong query rewrite traps spanning all major semantic discrepancy categories
TRAP_CASES_V2: list[dict[str, Any]] = [
    # 1. NOT IN vs NOT EXISTS with NULLs
    {
        "id": "trap_01_not_in_nulls",
        "category": "not_in_null",
        "orig": "SELECT id FROM orders WHERE customer_id NOT IN (SELECT id FROM banned WHERE id IS NOT NULL);",
        "cand": "SELECT id FROM orders WHERE customer_id NOT IN (SELECT id FROM banned);",
    },
    # 2. UNION to UNION ALL
    {
        "id": "trap_02_union_to_all",
        "category": "union_all",
        "orig": "SELECT status FROM orders UNION SELECT category FROM items;",
        "cand": "SELECT status FROM orders UNION ALL SELECT category FROM items;",
    },
    # 3. Dropping DISTINCT
    {
        "id": "trap_03_drop_distinct",
        "category": "distinct",
        "orig": "SELECT DISTINCT category FROM items;",
        "cand": "SELECT category FROM items;",
    },
    # 4. Adding unneeded DISTINCT
    {
        "id": "trap_04_add_distinct",
        "category": "distinct",
        "orig": "SELECT username FROM users;",
        "cand": "SELECT DISTINCT username FROM users;",
    },
    # 5. LEFT JOIN to INNER JOIN
    {
        "id": "trap_05_outer_to_inner",
        "category": "outer_join",
        "orig": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id;",
        "cand": "SELECT u.id, o.amount FROM users u INNER JOIN orders o ON u.id = o.user_id;",
    },
    # 6. Predicate pushdown across LEFT JOIN
    {
        "id": "trap_06_pushdown_outer",
        "category": "outer_join_pushdown",
        "orig": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id WHERE o.amount > 100 OR o.amount IS NULL;",
        "cand": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id AND o.amount > 100;",
    },
    # 7. Non-deterministic LIMIT without ORDER BY tie-breaker
    {
        "id": "trap_07_limit_ties",
        "category": "limit_ties",
        "orig": "SELECT id, score FROM items ORDER BY score DESC, id ASC LIMIT 2;",
        "cand": "SELECT id, score FROM items ORDER BY score DESC LIMIT 2;",
    },
    # 8. COUNT(*) vs COUNT(col) with NULLs
    {
        "id": "trap_08_count_col_nulls",
        "category": "aggregate_null",
        "orig": "SELECT COUNT(*) AS cnt FROM users;",
        "cand": "SELECT COUNT(phone) AS cnt FROM users;",
    },
    # 9. HAVING vs WHERE filter swap
    {
        "id": "trap_09_having_vs_where",
        "category": "having_clause",
        "orig": "SELECT category, SUM(score) FROM items GROUP BY category HAVING category = 'A';",
        "cand": "SELECT category, SUM(score) FROM items WHERE score > 0 GROUP BY category;",
    },
    # 10. Correlated subquery to JOIN with duplicate fan-out
    {
        "id": "trap_10_subquery_to_join_dups",
        "category": "fanout_join",
        "orig": "SELECT o.id FROM orders o WHERE o.amount > (SELECT AVG(oi.price) FROM order_items oi WHERE oi.order_id = o.id);",
        "cand": "SELECT o.id FROM orders o JOIN order_items oi ON o.id = oi.order_id WHERE o.amount > oi.price;",
    },
    # 11. NOT IN subquery with OR NULL
    {
        "id": "trap_11_not_in_or",
        "category": "not_in_null",
        "orig": "SELECT id FROM items WHERE id NOT IN (SELECT id FROM banned WHERE id > 0);",
        "cand": "SELECT id FROM items WHERE id NOT IN (SELECT id FROM banned);",
    },
    # 12. Empty table aggregate: COUNT(*) in subquery vs outer count
    {
        "id": "trap_12_empty_group_count",
        "category": "empty_table",
        "orig": "SELECT category, COUNT(score) FROM items GROUP BY category;",
        "cand": "SELECT category, COUNT(*) FROM items GROUP BY category;",
    },
    # 13. Off-by-one boundary shift
    {
        "id": "trap_13_off_by_one",
        "category": "boundary",
        "orig": "SELECT id FROM users WHERE age > 21;",
        "cand": "SELECT id FROM users WHERE age >= 21;",
    },
    # 14. Integer division truncation
    {
        "id": "trap_14_int_div",
        "category": "type_cast",
        "orig": "SELECT id, score / 2.0 AS s FROM items;",
        "cand": "SELECT id, score / 2 AS s FROM items;",
    },
    # 15. Negation with NULLs
    {
        "id": "trap_15_negation_nulls",
        "category": "null_logic",
        "orig": "SELECT id FROM users WHERE col <= 10 OR col IS NULL;",
        "cand": "SELECT id FROM users WHERE col <= 10;",
    },
    # 16. LEFT JOIN ON condition moved to WHERE
    {
        "id": "trap_16_left_join_where",
        "category": "outer_join",
        "orig": "SELECT u.id FROM users u LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'active';",
        "cand": "SELECT u.id FROM users u LEFT JOIN orders o ON u.id = o.user_id WHERE o.status = 'active';",
    },
    # 17. AVG vs SUM / COUNT(*) with NULLs
    {
        "id": "trap_17_avg_nulls",
        "category": "aggregate_null",
        "orig": "SELECT AVG(score) FROM items;",
        "cand": "SELECT SUM(score) * 1.0 / COUNT(*) FROM items;",
    },
    # 18. CASE missing ELSE branch (defaults to NULL)
    {
        "id": "trap_18_case_no_else",
        "category": "case_logic",
        "orig": "SELECT CASE WHEN val > 0 THEN 'pos' ELSE 'other' END FROM items;",
        "cand": "SELECT CASE WHEN val > 0 THEN 'pos' END FROM items;",
    },
    # 19. COALESCE argument ordering
    {
        "id": "trap_19_coalesce_order",
        "category": "coalesce",
        "orig": "SELECT COALESCE(email, phone, 'none') FROM users;",
        "cand": "SELECT COALESCE(phone, email, 'none') FROM users;",
    },
    # 20. LIKE vs exact equality
    {
        "id": "trap_20_like_vs_eq",
        "category": "string_matching",
        "orig": "SELECT id FROM users WHERE username = 'admin%';",
        "cand": "SELECT id FROM users WHERE username LIKE 'admin%';",
    },
    # 21. MAX() vs LIMIT 1 on empty table
    {
        "id": "trap_21_max_vs_limit",
        "category": "empty_table",
        "orig": "SELECT MAX(score) FROM items;",
        "cand": "SELECT score FROM items ORDER BY score DESC LIMIT 1;",
    },
    # 22. IN subquery replaced by non-distinct JOIN
    {
        "id": "trap_22_subquery_in_vs_join",
        "category": "duplicate_join",
        "orig": "SELECT id FROM orders WHERE id IN (SELECT order_id FROM order_items);",
        "cand": "SELECT o.id FROM orders o JOIN order_items oi ON o.id = oi.order_id;",
    },
    # 23. Window frame order by running sum vs partition sum
    {
        "id": "trap_23_window_frame_order",
        "category": "window_frame",
        "orig": "SELECT id, SUM(val) OVER (PARTITION BY category) FROM items;",
        "cand": "SELECT id, SUM(val) OVER (PARTITION BY category ORDER BY id) FROM items;",
    },
    # 24. Unintended sign change
    {
        "id": "trap_24_sign_flip",
        "category": "arithmetic",
        "orig": "SELECT id, -val FROM items;",
        "cand": "SELECT id, val FROM items;",
    },
    # 25. Boolean operator precedence AND vs OR
    {
        "id": "trap_25_operator_precedence",
        "category": "boolean_precedence",
        "orig": "SELECT id FROM items WHERE active = 1 AND (priority = 1 OR flagged = 1);",
        "cand": "SELECT id FROM items WHERE active = 1 AND priority = 1 OR flagged = 1;",
    },
    # 26. ANY vs ALL in subquery (quantified aggregation)
    {
        "id": "trap_26_any_vs_all",
        "category": "quantified_comparison",
        "orig": "SELECT id FROM items WHERE val > (SELECT MAX(val) FROM items WHERE val < 10);",
        "cand": "SELECT id FROM items WHERE val > (SELECT MIN(val) FROM items WHERE val < 10);",
    },
    # 27. Window frame ROWS BETWEEN 1 PRECEDING vs CURRENT ROW
    {
        "id": "trap_27_window_frame_bounds",
        "category": "window_frame",
        "orig": "SELECT id, SUM(val) OVER (ORDER BY id ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING) FROM items;",
        "cand": "SELECT id, SUM(val) OVER (ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) FROM items;",
    },
    # 28. COUNT(DISTINCT col) vs COUNT(col)
    {
        "id": "trap_28_count_distinct",
        "category": "distinct_aggregate",
        "orig": "SELECT COUNT(DISTINCT status) FROM orders;",
        "cand": "SELECT COUNT(status) FROM orders;",
    },
    # 29. NULLIF vs COALESCE
    {
        "id": "trap_29_nullif_vs_coalesce",
        "category": "null_functions",
        "orig": "SELECT NULLIF(score, 0) FROM items;",
        "cand": "SELECT COALESCE(score, 0) FROM items;",
    },
    # 30. Uncorrelated EXISTS subquery replacing correlated subquery
    {
        "id": "trap_30_uncorrelated_exists",
        "category": "subquery_correlation",
        "orig": "SELECT u.id FROM users u WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id);",
        "cand": "SELECT u.id FROM users u WHERE EXISTS (SELECT 1 FROM orders o);",
    },
    # 31. De Morgan law violation: NOT (a AND b) vs (NOT a AND NOT b)
    {
        "id": "trap_31_de_morgan_violation",
        "category": "boolean_logic",
        "orig": "SELECT id FROM items WHERE NOT (active = 1 AND priority = 1);",
        "cand": "SELECT id FROM items WHERE active <> 1 AND priority <> 1;",
    },
    # 32. String concatenation NULL propagation
    {
        "id": "trap_32_concat_null_propagation",
        "category": "string_null",
        "orig": "SELECT id, username || ' - ' || COALESCE(phone, 'N/A') FROM users;",
        "cand": "SELECT id, username || ' - ' || phone FROM users;",
    },
    # 33. Dropping ORDER BY before LIMIT
    {
        "id": "trap_33_drop_order_by_limit",
        "category": "limit_ordering",
        "orig": "SELECT id, score FROM items ORDER BY score ASC LIMIT 3;",
        "cand": "SELECT id, score FROM items LIMIT 3;",
    },
    # 34. IN subquery with NULL in left operand
    {
        "id": "trap_34_in_null_left",
        "category": "not_in_null",
        "orig": "SELECT id FROM items WHERE score IN (SELECT id FROM users) OR score IS NULL;",
        "cand": "SELECT id FROM items WHERE score IN (SELECT id FROM users);",
    },
    # 35. Decimal ROUND to int vs fractional ROUND
    {
        "id": "trap_35_round_precision",
        "category": "rounding",
        "orig": "SELECT id, ROUND(amount, 2) FROM orders;",
        "cand": "SELECT id, ROUND(amount, 0) FROM orders;",
    },
    # 36. SUM(x) + SUM(y) vs SUM(x + y) when x or y is NULL
    {
        "id": "trap_36_sum_add_nulls",
        "category": "aggregate_null",
        "orig": "SELECT COALESCE(SUM(x), 0) + COALESCE(SUM(y), 0) FROM items;",
        "cand": "SELECT SUM(x + y) FROM items;",
    },
    # 37. LEFT JOIN turned into FULL OUTER JOIN
    {
        "id": "trap_37_left_to_full_outer",
        "category": "outer_join",
        "orig": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id;",
        "cand": "SELECT u.id, o.amount FROM users u FULL OUTER JOIN orders o ON u.id = o.user_id;",
    },
    # 38. Filter condition in WHERE of FULL OUTER JOIN converting it to INNER
    {
        "id": "trap_38_full_outer_where_null",
        "category": "outer_join",
        "orig": "SELECT u.id, o.id FROM users u FULL OUTER JOIN orders o ON u.id = o.user_id;",
        "cand": "SELECT u.id, o.id FROM users u FULL OUTER JOIN orders o ON u.id = o.user_id WHERE u.age > 18;",
    },
    # 39. Handling NULL in multi-column comparison vs simplistic CASE WHEN
    {
        "id": "trap_39_greatest_null_semantics",
        "category": "greatest_least",
        "orig": "SELECT id, CASE WHEN x IS NULL THEN y WHEN y IS NULL THEN x WHEN x >= y THEN x ELSE y END FROM items;",
        "cand": "SELECT id, CASE WHEN x >= y THEN x ELSE y END FROM items;",
    },
    # 40. Duplicate elimination vs multiset preservation in difference
    {
        "id": "trap_40_except_vs_all",
        "category": "set_operations",
        "orig": "SELECT val FROM t1 WHERE val NOT IN (SELECT val FROM t2 WHERE val IS NOT NULL);",
        "cand": "SELECT DISTINCT val FROM t1 WHERE val NOT IN (SELECT val FROM t2 WHERE val IS NOT NULL);",
    },
    # 41. EXISTS vs INNER JOIN causing row amplification on duplicate matches
    {
        "id": "trap_41_intersect_vs_all",
        "category": "set_operations",
        "orig": "SELECT u.id FROM users u WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.amount > 100);",
        "cand": "SELECT u.id FROM users u INNER JOIN orders o ON u.id = o.user_id AND o.amount > 100;",
    },
    # 42. Inverting BETWEEN range bounds (SQL BETWEEN yields empty set if low > high)
    {
        "id": "trap_42_between_inverted_bounds",
        "category": "between_bounds",
        "orig": "SELECT id FROM items WHERE val >= 10 AND val <= 50;",
        "cand": "SELECT id FROM items WHERE val BETWEEN 50 AND 10;",
    },
    # 43. Subquery column mismatch in IN
    {
        "id": "trap_43_subquery_col_mismatch",
        "category": "subquery",
        "orig": "SELECT id FROM orders WHERE user_id IN (SELECT id FROM users WHERE active = 1);",
        "cand": "SELECT id FROM orders WHERE user_id IN (SELECT age FROM users WHERE active = 1);",
    },
    # 44. Dropping GROUP BY column in aggregate projection
    {
        "id": "trap_44_drop_groupby_col",
        "category": "group_by",
        "orig": "SELECT category, status, COUNT(*) FROM items GROUP BY category, status;",
        "cand": "SELECT category, COUNT(*) FROM items GROUP BY category;",
    },
    # 45. Dropping IS NULL condition in disjunctive filter
    {
        "id": "trap_45_invert_comparison_nulls",
        "category": "null_logic",
        "orig": "SELECT id FROM items WHERE score IS NULL OR score = 100;",
        "cand": "SELECT id FROM items WHERE score = 100;",
    },
    # 46. Replacing subquery scalar with unnested join (causing row amplification)
    {
        "id": "trap_46_subquery_amplification",
        "category": "fanout_join",
        "orig": "SELECT u.id, (SELECT o.amount FROM orders o WHERE o.user_id = u.id LIMIT 1) FROM users u;",
        "cand": "SELECT u.id, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id;",
    },
    # 47. Incorrect IS DISTINCT FROM vs <> on NULLable columns
    {
        "id": "trap_47_is_distinct_from_vs_neq",
        "category": "distinct_from",
        "orig": "SELECT id FROM items WHERE x IS DISTINCT FROM y;",
        "cand": "SELECT id FROM items WHERE x <> y;",
    },
    # 48. Replacing string prefix extraction with entire string
    {
        "id": "trap_48_trim_vs_substring",
        "category": "string_functions",
        "orig": "SELECT id, SUBSTRING(category, 1, 3) FROM items;",
        "cand": "SELECT id, category FROM items;",
    },
    # 49. ROW_NUMBER() vs RANK() when duplicates/ties exist
    {
        "id": "trap_49_rownum_vs_rank",
        "category": "window_functions",
        "orig": "SELECT id, ROW_NUMBER() OVER (PARTITION BY category ORDER BY val) FROM items;",
        "cand": "SELECT id, RANK() OVER (PARTITION BY category ORDER BY val) FROM items;",
    },
    # 50. Dropping DISTINCT inside COUNT(DISTINCT)
    {
        "id": "trap_50_count_distinct_drop",
        "category": "distinct_aggregate",
        "orig": "SELECT category, COUNT(DISTINCT serial_no) FROM items GROUP BY category;",
        "cand": "SELECT category, COUNT(serial_no) FROM items GROUP BY category;",
    },
]
