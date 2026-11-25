"""
@file perf_suite.py
@description Performance Suite: 30 representative PostgreSQL queries (including TPC-H-derived benchmarks)
@module eval/suites/perf_suite
"""

from typing import Any

from sqldoctor.schema.models import (
    ColumnModel,
    ConstraintModel,
    ConstraintType,
    SchemaModel,
    TableModel,
)


def get_perf_suite_schema() -> SchemaModel:
    """Build relational schema modeled after standard analytical decision-support schemas (TPC-H style)."""
    customer_tbl = TableModel(
        name="customer",
        columns={
            "c_custkey": ColumnModel(name="c_custkey", data_type="integer", is_nullable=False),
            "c_name": ColumnModel(name="c_name", data_type="varchar", is_nullable=False),
            "c_nationkey": ColumnModel(name="c_nationkey", data_type="integer", is_nullable=False),
            "c_phone": ColumnModel(name="c_phone", data_type="varchar", is_nullable=False),
            "c_acctbal": ColumnModel(name="c_acctbal", data_type="numeric", is_nullable=False),
            "c_mktsegment": ColumnModel(
                name="c_mktsegment", data_type="varchar", is_nullable=False
            ),
        },
        constraints=[
            ConstraintModel(
                name="pk_customer", type=ConstraintType.PRIMARY_KEY, columns=["c_custkey"]
            )
        ],
    )

    orders_tbl = TableModel(
        name="orders",
        columns={
            "o_orderkey": ColumnModel(name="o_orderkey", data_type="integer", is_nullable=False),
            "o_custkey": ColumnModel(name="o_custkey", data_type="integer", is_nullable=False),
            "o_orderstatus": ColumnModel(
                name="o_orderstatus", data_type="varchar", is_nullable=False
            ),
            "o_totalprice": ColumnModel(
                name="o_totalprice", data_type="numeric", is_nullable=False
            ),
            "o_orderdate": ColumnModel(name="o_orderdate", data_type="varchar", is_nullable=False),
            "o_orderpriority": ColumnModel(
                name="o_orderpriority", data_type="varchar", is_nullable=False
            ),
        },
        constraints=[
            ConstraintModel(
                name="pk_orders", type=ConstraintType.PRIMARY_KEY, columns=["o_orderkey"]
            )
        ],
    )

    lineitem_tbl = TableModel(
        name="lineitem",
        columns={
            "l_orderkey": ColumnModel(name="l_orderkey", data_type="integer", is_nullable=False),
            "l_partkey": ColumnModel(name="l_partkey", data_type="integer", is_nullable=False),
            "l_suppkey": ColumnModel(name="l_suppkey", data_type="integer", is_nullable=False),
            "l_quantity": ColumnModel(name="l_quantity", data_type="numeric", is_nullable=False),
            "l_extendedprice": ColumnModel(
                name="l_extendedprice", data_type="numeric", is_nullable=False
            ),
            "l_discount": ColumnModel(name="l_discount", data_type="numeric", is_nullable=False),
            "l_tax": ColumnModel(name="l_tax", data_type="numeric", is_nullable=False),
            "l_returnflag": ColumnModel(
                name="l_returnflag", data_type="varchar", is_nullable=False
            ),
            "l_linestatus": ColumnModel(
                name="l_linestatus", data_type="varchar", is_nullable=False
            ),
            "l_shipdate": ColumnModel(name="l_shipdate", data_type="varchar", is_nullable=False),
        },
    )

    part_tbl = TableModel(
        name="part",
        columns={
            "p_partkey": ColumnModel(name="p_partkey", data_type="integer", is_nullable=False),
            "p_name": ColumnModel(name="p_name", data_type="varchar", is_nullable=False),
            "p_brand": ColumnModel(name="p_brand", data_type="varchar", is_nullable=False),
            "p_type": ColumnModel(name="p_type", data_type="varchar", is_nullable=False),
            "p_size": ColumnModel(name="p_size", data_type="integer", is_nullable=False),
            "p_retailprice": ColumnModel(
                name="p_retailprice", data_type="numeric", is_nullable=False
            ),
        },
        constraints=[
            ConstraintModel(name="pk_part", type=ConstraintType.PRIMARY_KEY, columns=["p_partkey"])
        ],
    )

    supplier_tbl = TableModel(
        name="supplier",
        columns={
            "s_suppkey": ColumnModel(name="s_suppkey", data_type="integer", is_nullable=False),
            "s_name": ColumnModel(name="s_name", data_type="varchar", is_nullable=False),
            "s_nationkey": ColumnModel(name="s_nationkey", data_type="integer", is_nullable=False),
            "s_phone": ColumnModel(name="s_phone", data_type="varchar", is_nullable=False),
            "s_acctbal": ColumnModel(name="s_acctbal", data_type="numeric", is_nullable=False),
        },
        constraints=[
            ConstraintModel(
                name="pk_supplier", type=ConstraintType.PRIMARY_KEY, columns=["s_suppkey"]
            )
        ],
    )

    return SchemaModel(
        tables={
            "customer": customer_tbl,
            "orders": orders_tbl,
            "lineitem": lineitem_tbl,
            "part": part_tbl,
            "supplier": supplier_tbl,
        }
    )


# 30 Representative analytical and transactional benchmark queries
PERF_CASES_V1: list[dict[str, Any]] = [
    # 1. TPC-H Q1 Pricing Summary Report
    {
        "id": "perf_01_pricing_summary",
        "name": "TPC-H Q1 Pricing Summary",
        "orig": "SELECT l_returnflag, l_linestatus, SUM(l_quantity) AS sum_qty, SUM(l_extendedprice) AS sum_base_price, AVG(l_quantity) AS avg_qty FROM lineitem GROUP BY l_returnflag, l_linestatus;",
        "cand": "SELECT l_returnflag, l_linestatus, SUM(l_quantity) AS sum_qty, SUM(l_extendedprice) AS sum_base_price, AVG(l_quantity) AS avg_qty FROM lineitem GROUP BY l_returnflag, l_linestatus;",
    },
    # 2. TPC-H Q6 Forecasting Revenue Change (selective range scan)
    {
        "id": "perf_02_forecasting_revenue",
        "name": "TPC-H Q6 Range Scan",
        "orig": "SELECT SUM(l_extendedprice * l_discount) AS revenue FROM lineitem WHERE l_shipdate >= '1994-01-01' AND l_shipdate <= '1995-01-01' AND l_discount >= 0.05 AND l_discount <= 0.07 AND l_quantity < 24;",
        "cand": "SELECT SUM(l_extendedprice * l_discount) AS revenue FROM lineitem WHERE l_shipdate BETWEEN '1994-01-01' AND '1995-01-01' AND l_discount BETWEEN 0.05 AND 0.07 AND l_quantity < 24;",
    },
    # 3. TPC-H Q3 Shipping Priority (comma join to explicit join)
    {
        "id": "perf_03_shipping_priority",
        "name": "TPC-H Q3 3-Table Join",
        "orig": "SELECT l.l_orderkey, SUM(l.l_extendedprice) AS revenue, o.o_orderdate FROM customer c, orders o, lineitem l WHERE c.c_mktsegment = 'BUILDING' AND c.c_custkey = o.o_custkey AND l.l_orderkey = o.o_orderkey GROUP BY l.l_orderkey, o.o_orderdate;",
        "cand": "SELECT l.l_orderkey, SUM(l.l_extendedprice) AS revenue, o.o_orderdate FROM customer c INNER JOIN orders o ON c.c_custkey = o.o_custkey INNER JOIN lineitem l ON l.l_orderkey = o.o_orderkey WHERE c.c_mktsegment = 'BUILDING' GROUP BY l.l_orderkey, o.o_orderdate;",
    },
    # 4. TPC-H Q4 Order Priority Checking (EXISTS subquery)
    {
        "id": "perf_04_order_priority",
        "name": "TPC-H Q4 Order Priority",
        "orig": "SELECT o.o_orderpriority, COUNT(*) AS order_count FROM orders o WHERE o.o_orderkey IN (SELECT l.l_orderkey FROM lineitem l) GROUP BY o.o_orderpriority;",
        "cand": "SELECT o.o_orderpriority, COUNT(*) AS order_count FROM orders o WHERE EXISTS (SELECT 1 FROM lineitem l WHERE l.l_orderkey = o.o_orderkey) GROUP BY o.o_orderpriority;",
    },
    # 5. Customer account balance aggregation
    {
        "id": "perf_05_cust_acctbal_agg",
        "name": "Customer Segment Balances",
        "orig": "SELECT c_mktsegment, AVG(c_acctbal) FROM customer WHERE c_acctbal > 0 GROUP BY c_mktsegment;",
        "cand": "SELECT c_mktsegment, AVG(c_acctbal) FROM customer WHERE c_acctbal > 0.0 GROUP BY c_mktsegment;",
    },
    # 6. Part brand and type filtering
    {
        "id": "perf_06_part_brand_filtering",
        "name": "Part Sizing Scan",
        "orig": "SELECT p_partkey, p_retailprice FROM part WHERE (p_brand = 'Brand#12' OR p_brand = 'Brand#23') AND p_size >= 10 AND p_size <= 20;",
        "cand": "SELECT p_partkey, p_retailprice FROM part WHERE p_brand IN ('Brand#12', 'Brand#23') AND p_size BETWEEN 10 AND 20;",
    },
    # 7. High-value order customer join
    {
        "id": "perf_07_high_value_orders",
        "name": "High Value Orders",
        "orig": "SELECT c.c_name, o.o_totalprice FROM customer c, orders o WHERE c.c_custkey = o.o_custkey AND o.o_totalprice > 1000;",
        "cand": "SELECT c.c_name, o.o_totalprice FROM customer c INNER JOIN orders o ON c.c_custkey = o.o_custkey WHERE o.o_totalprice > 1000;",
    },
    # 8. Order status breakdown
    {
        "id": "perf_08_order_status_count",
        "name": "Order Status Counts",
        "orig": "SELECT o_orderstatus, COUNT(o_orderkey) FROM orders GROUP BY o_orderstatus;",
        "cand": "SELECT o_orderstatus, COUNT(*) FROM orders GROUP BY o_orderstatus;",
    },
    # 9. Supplier nation balance
    {
        "id": "perf_09_supplier_nation_bal",
        "name": "Supplier Balances",
        "orig": "SELECT s_nationkey, SUM(s_acctbal) FROM supplier WHERE s_acctbal > 500 GROUP BY s_nationkey;",
        "cand": "SELECT s_nationkey, SUM(s_acctbal) FROM supplier WHERE s_acctbal > 500.0 GROUP BY s_nationkey;",
    },
    # 10. Multi-item quantity total
    {
        "id": "perf_10_lineitem_quantities",
        "name": "Lineitem Quantity Totals",
        "orig": "SELECT l_orderkey, SUM(l_quantity + 0) FROM lineitem GROUP BY l_orderkey;",
        "cand": "SELECT l_orderkey, SUM(l_quantity) FROM lineitem GROUP BY l_orderkey;",
    },
    # 11. Large discount orders
    {
        "id": "perf_11_large_discounts",
        "name": "Discount Filtering",
        "orig": "SELECT l_orderkey, l_extendedprice FROM lineitem WHERE l_discount > 0.08 AND l_quantity < 10;",
        "cand": "SELECT l_orderkey, l_extendedprice FROM lineitem WHERE l_discount > 0.08 AND l_quantity < 10;",
    },
    # 12. Active order status filter
    {
        "id": "perf_12_active_status",
        "name": "Active Order Lookup",
        "orig": "SELECT o_orderkey, o_custkey FROM orders WHERE o_orderstatus = 'O' OR o_orderstatus = 'P';",
        "cand": "SELECT o_orderkey, o_custkey FROM orders WHERE o_orderstatus IN ('O', 'P');",
    },
    # 13. Customer segment nation grouping
    {
        "id": "perf_13_cust_nation_group",
        "name": "Nation Segment Counts",
        "orig": "SELECT c_nationkey, c_mktsegment, COUNT(*) FROM customer GROUP BY c_nationkey, c_mktsegment;",
        "cand": "SELECT c_nationkey, c_mktsegment, COUNT(*) FROM customer GROUP BY c_nationkey, c_mktsegment;",
    },
    # 14. High quantity lineitems
    {
        "id": "perf_14_high_qty_lineitems",
        "name": "High Quantity Lines",
        "orig": "SELECT l_partkey, l_quantity FROM lineitem WHERE l_quantity > 40 AND l_quantity < 100;",
        "cand": "SELECT l_partkey, l_quantity FROM lineitem WHERE l_quantity > 40 AND l_quantity < 100;",
    },
    # 15. Part price threshold
    {
        "id": "perf_15_part_price_threshold",
        "name": "Part Price Filter",
        "orig": "SELECT p_partkey, p_retailprice * 1.0 FROM part WHERE p_retailprice > 500;",
        "cand": "SELECT p_partkey, p_retailprice FROM part WHERE p_retailprice > 500;",
    },
    # 16. Supplier phone prefix search
    {
        "id": "perf_16_supplier_phone",
        "name": "Supplier Phone Search",
        "orig": "SELECT s_suppkey, s_name FROM supplier WHERE s_phone LIKE '11-%';",
        "cand": "SELECT s_suppkey, s_name FROM supplier WHERE s_phone LIKE '11-%';",
    },
    # 17. Orders priority breakdown
    {
        "id": "perf_17_orders_priority",
        "name": "Order Priority Group",
        "orig": "SELECT o_orderpriority, SUM(o_totalprice) FROM orders GROUP BY o_orderpriority;",
        "cand": "SELECT o_orderpriority, SUM(o_totalprice) FROM orders GROUP BY o_orderpriority;",
    },
    # 18. Lineitem return flag analysis
    {
        "id": "perf_18_return_flag_analysis",
        "name": "Return Flag Groups",
        "orig": "SELECT l_returnflag, AVG(l_discount) FROM lineitem GROUP BY l_returnflag;",
        "cand": "SELECT l_returnflag, AVG(l_discount) FROM lineitem GROUP BY l_returnflag;",
    },
    # 19. Customer positive balance list
    {
        "id": "perf_19_cust_pos_bal",
        "name": "Positive Balance Customers",
        "orig": "SELECT c_custkey, c_name FROM customer WHERE c_acctbal > 0;",
        "cand": "SELECT c_custkey, c_name FROM customer WHERE c_acctbal > 0.0;",
    },
    # 20. Order price bounds
    {
        "id": "perf_20_order_price_bounds",
        "name": "Order Total Bounds",
        "orig": "SELECT o_orderkey, o_totalprice FROM orders WHERE o_totalprice >= 100 AND o_totalprice <= 500;",
        "cand": "SELECT o_orderkey, o_totalprice FROM orders WHERE o_totalprice BETWEEN 100 AND 500;",
    },
    # 21. Multi-part sizing
    {
        "id": "perf_21_multipart_sizing",
        "name": "Part Sizing In-List",
        "orig": "SELECT p_partkey FROM part WHERE p_size = 1 OR p_size = 5 OR p_size = 10;",
        "cand": "SELECT p_partkey FROM part WHERE p_size IN (1, 5, 10);",
    },
    # 22. Lineitem tax calculation
    {
        "id": "perf_22_lineitem_tax",
        "name": "Tax Aggregation",
        "orig": "SELECT l_partkey, SUM(l_extendedprice * (1 + l_tax)) FROM lineitem GROUP BY l_partkey;",
        "cand": "SELECT l_partkey, SUM(l_extendedprice * (1.0 + l_tax)) FROM lineitem GROUP BY l_partkey;",
    },
    # 23. Customer order count subquery
    {
        "id": "perf_23_cust_order_subquery",
        "name": "Customer Orders Subquery",
        "orig": "SELECT c.c_custkey, c.c_name FROM customer c WHERE c.c_custkey IN (SELECT o.o_custkey FROM orders o);",
        "cand": "SELECT c.c_custkey, c.c_name FROM customer c WHERE EXISTS (SELECT 1 FROM orders o WHERE o.o_custkey = c.c_custkey);",
    },
    # 24. Supplier negative balance alert
    {
        "id": "perf_24_supplier_neg_bal",
        "name": "Negative Balance Suppliers",
        "orig": "SELECT s_suppkey, s_name FROM supplier WHERE s_acctbal < 0;",
        "cand": "SELECT s_suppkey, s_name FROM supplier WHERE s_acctbal < 0.0;",
    },
    # 25. High quantity order lines
    {
        "id": "perf_25_high_qty_orders",
        "name": "High Quantity Lines",
        "orig": "SELECT l_orderkey, l_quantity FROM lineitem WHERE l_quantity > 45;",
        "cand": "SELECT l_orderkey, l_quantity FROM lineitem WHERE l_quantity > 45.0;",
    },
    # 26. Part retail price discount projection
    {
        "id": "perf_26_part_price_disc",
        "name": "Part Price Projection",
        "orig": "SELECT p_partkey, p_retailprice * 0.9 AS disc_price FROM part;",
        "cand": "SELECT p_partkey, p_retailprice * 0.90 AS disc_price FROM part;",
    },
    # 27. Orders date range
    {
        "id": "perf_27_orders_date_range",
        "name": "Order Date Range",
        "orig": "SELECT o_orderkey FROM orders WHERE o_orderdate >= '1995-01-01' AND o_orderdate <= '1995-12-31';",
        "cand": "SELECT o_orderkey FROM orders WHERE o_orderdate BETWEEN '1995-01-01' AND '1995-12-31';",
    },
    # 28. Lineitem ship date scan
    {
        "id": "perf_28_lineitem_ship_scan",
        "name": "Ship Date Range",
        "orig": "SELECT l_orderkey, l_shipdate FROM lineitem WHERE l_shipdate >= '1996-01-01' AND l_shipdate <= '1996-06-30';",
        "cand": "SELECT l_orderkey, l_shipdate FROM lineitem WHERE l_shipdate BETWEEN '1996-01-01' AND '1996-06-30';",
    },
    # 29. Customer nation balance average
    {
        "id": "perf_29_cust_nation_avg",
        "name": "Nation Average Balances",
        "orig": "SELECT c_nationkey, AVG(c_acctbal) FROM customer GROUP BY c_nationkey;",
        "cand": "SELECT c_nationkey, AVG(c_acctbal) FROM customer GROUP BY c_nationkey;",
    },
    # 30. Lineitem discount average by linestatus
    {
        "id": "perf_30_lineitem_disc_avg",
        "name": "Line Status Discount Avg",
        "orig": "SELECT l_linestatus, AVG(l_discount) FROM lineitem GROUP BY l_linestatus;",
        "cand": "SELECT l_linestatus, AVG(l_discount) FROM lineitem GROUP BY l_linestatus;",
    },
]
