"""
@file test_roundtrip.py
@description Gate test verifying sqlglot round-trips 20 complex PostgreSQL queries
@module tests/test_roundtrip
"""

import pytest

from sqldoctor.sql.ast import parse_sql, round_trip

# 20 realistic, complex PostgreSQL queries covering critical SQL constructs
SAMPLE_QUERIES = [
    # 1. Common Table Expression (CTE) with aggregate
    """
    WITH regional_sales AS (
        SELECT region, SUM(amount) AS total_sales
        FROM orders
        GROUP BY region
    )
    SELECT region, total_sales
    FROM regional_sales
    WHERE total_sales > 10000;
    """,
    # 2. Window function with PARTITION BY and ORDER BY
    """
    SELECT emp_id, dept_id, salary,
           ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) AS rank
    FROM employees;
    """,
    # 3. Aggregate FILTER clause
    """
    SELECT dept_id,
           COUNT(*) AS total_emps,
           COUNT(*) FILTER (WHERE salary > 50000) AS high_earners
    FROM employees
    GROUP BY dept_id;
    """,
    # 4. Correlated subquery with EXISTS
    """
    SELECT c.customer_id, c.full_name
    FROM customers c
    WHERE EXISTS (
        SELECT 1 FROM orders o
        WHERE o.customer_id = c.customer_id AND o.status = 'completed'
    );
    """,
    # 5. NOT IN subquery
    """
    SELECT p.product_id, p.name
    FROM products p
    WHERE p.product_id NOT IN (
        SELECT oi.product_id
        FROM order_items oi
        WHERE oi.product_id IS NOT NULL
    );
    """,
    # 6. Full Outer Join with COALESCE
    """
    SELECT COALESCE(a.id, b.id) AS unified_id, a.val_a, b.val_b
    FROM table_a a
    FULL OUTER JOIN table_b b ON a.id = b.id;
    """,
    # 7. Recursive CTE
    """
    WITH RECURSIVE subordinates AS (
        SELECT emp_id, manager_id, full_name, 1 AS level
        FROM employees
        WHERE manager_id IS NULL
        UNION ALL
        SELECT e.emp_id, e.manager_id, e.full_name, s.level + 1
        FROM employees e
        INNER JOIN subordinates s ON s.emp_id = e.manager_id
    )
    SELECT emp_id, full_name, level FROM subordinates;
    """,
    # 8. Set operations: EXCEPT ALL and UNION ALL
    """
    SELECT id, name FROM archived_users
    UNION ALL
    (
        SELECT id, name FROM active_users
        EXCEPT ALL
        SELECT id, name FROM banned_users
    );
    """,
    # 9. JSONB operator and extraction
    """
    SELECT doc_id, metadata->>'title' AS title, (metadata->'tags')::text AS tags
    FROM documents
    WHERE metadata @> '{"published": true}'::jsonb;
    """,
    # 10. Date / Timestamp interval arithmetic
    """
    SELECT event_id, recorded_at
    FROM telemetry
    WHERE recorded_at >= (NOW() - INTERVAL '7 days')
      AND recorded_at < NOW();
    """,
    # 11. CASE expression in projection and WHERE
    """
    SELECT item_id,
           CASE
               WHEN quantity = 0 THEN 'OUT_OF_STOCK'
               WHEN quantity < 10 THEN 'LOW_STOCK'
               ELSE 'IN_STOCK'
           END AS stock_status
    FROM inventory
    WHERE (CASE WHEN active THEN 1 ELSE 0 END) = 1;
    """,
    # 12. Array containment and UNNEST
    """
    SELECT article_id, tag
    FROM articles,
    UNNEST(tags) AS tag
    WHERE 'database' = ANY(tags);
    """,
    # 13. CROSS JOIN LATERAL
    """
    SELECT d.dept_name, top_emp.name, top_emp.salary
    FROM departments d
    CROSS JOIN LATERAL (
        SELECT e.name, e.salary
        FROM employees e
        WHERE e.dept_id = d.dept_id
        ORDER BY e.salary DESC
        LIMIT 1
    ) AS top_emp;
    """,
    # 14. GROUPING SETS / ROLLUP
    """
    SELECT department, year, SUM(revenue) AS total_rev
    FROM annual_reports
    GROUP BY ROLLUP (department, year);
    """,
    # 15. DISTINCT ON clause
    """
    SELECT DISTINCT ON (customer_id) customer_id, order_id, ordered_at, order_total
    FROM orders
    ORDER BY customer_id, ordered_at DESC;
    """,
    # 16. Regular expression matching (~*) and string functions
    """
    SELECT user_id, email
    FROM users
    WHERE email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}$'
      AND LOWER(username) LIKE 'admin%';
    """,
    # 17. Explicit Type Casting and Numeric rounding
    """
    SELECT txn_id,
           ROUND(amount::numeric, 2) AS rounded_amount,
           (created_at AT TIME ZONE 'UTC')::date AS txn_date
    FROM transactions;
    """,
    # 18. Sliding Window Frame (ROWS BETWEEN)
    """
    SELECT reading_time, sensor_val,
           AVG(sensor_val) OVER (
               ORDER BY reading_time
               ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
           ) AS moving_avg
    FROM sensor_logs;
    """,
    # 19. Multi-table inner/left join with compound predicates
    """
    SELECT o.order_id, c.full_name, p.name AS product_name, oi.quantity, oi.unit_price
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    LEFT JOIN products p ON p.product_id = oi.sku
    WHERE o.status IN ('completed', 'shipped')
      AND (c.is_active = TRUE OR o.order_total > 500);
    """,
    # 20. HAVING clause with aggregate predicate
    """
    SELECT supplier_id,
           COUNT(product_id) AS total_products,
           AVG(unit_cost) AS avg_cost
    FROM supplies
    GROUP BY supplier_id
    HAVING COUNT(product_id) >= 5 AND AVG(unit_cost) < 50.0;
    """,
]


def test_twenty_sample_queries_count() -> None:
    """Ensure exactly 20 sample queries are tested as required by Phase 0 gate."""
    assert len(SAMPLE_QUERIES) == 20


@pytest.mark.parametrize("query_sql", SAMPLE_QUERIES)
def test_query_parses_and_roundtrips(query_sql: str) -> None:
    """Verify that every query parses to an AST and round-trips cleanly."""
    # 1. Parse check
    ast = parse_sql(query_sql)
    assert ast is not None

    # 2. Round-trip check
    is_equiv, first_sql, second_sql = round_trip(query_sql)
    assert is_equiv, f"Round-trip AST mismatch:\nFirst:\n{first_sql}\nSecond:\n{second_sql}"
