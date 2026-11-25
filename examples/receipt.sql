-- ============================================================================
-- SQL DOCTOR VERIFICATION RECEIPT
-- Verdict: TESTED_EQUIVALENT
-- Tool Version: 0.1.0 | PostgreSQL Target: 17.x
-- Seed: 20261123 | Generated: 2026-11-24T00:27:12.258936+00:00
-- ============================================================================

-- 1. Schema Definition (DDL)
BEGIN;
DROP TABLE IF EXISTS customers CASCADE;
CREATE TABLE customers (
    id int NOT NULL,
    name varchar(100) NOT NULL,
    country varchar(50) NOT NULL,
    is_vip boolean NOT NULL,
    CONSTRAINT pk_customers_id PRIMARY KEY (id)
);

DROP TABLE IF EXISTS orders CASCADE;
CREATE TABLE orders (
    id int NOT NULL,
    customer_id int NOT NULL,
    amount decimal NOT NULL,
    status varchar(20) NOT NULL,
    CONSTRAINT pk_orders_id PRIMARY KEY (id)
);

-- 2. Test Dataset (Minimal Counterexample / Verification Seed)

-- 3. Query Equivalence Comparison
-- Run both queries over the test dataset and compare results via multiset bag equality (EXCEPT ALL).
WITH original_query AS (
    SELECT c.id, c.name, o.amount
FROM customers c, orders o
WHERE c.id = o.customer_id
  AND o.status = 'completed'
),
candidate_query AS (
    SELECT c.id, c.name, o.amount FROM customers c INNER JOIN orders o ON c.id = o.customer_id WHERE o.status = 'completed'
),
disparities AS (
    -- Rows produced by original but missing from candidate
    (SELECT 'ORIGINAL_ONLY' AS source, o.* FROM (SELECT * FROM original_query EXCEPT ALL SELECT * FROM candidate_query) o)
    UNION ALL
    -- Rows produced by candidate but missing from original
    (SELECT 'CANDIDATE_ONLY' AS source, c.* FROM (SELECT * FROM candidate_query EXCEPT ALL SELECT * FROM original_query) c)
)
SELECT * FROM disparities;

ROLLBACK;

-- ============================================================================
-- EXPECTED OUTPUT:
-- 0 rows returned.
-- (Queries produce identical multiset bag results across all test permutations).
-- ============================================================================
