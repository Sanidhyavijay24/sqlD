"""
@file conftest.py
@description Pytest configuration and shared test fixtures
@module tests/conftest
"""

import sys
from pathlib import Path

import pytest

# Ensure src/ is on sys.path for test imports
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def sample_ecommerce_ddl() -> str:
    """Return realistic PostgreSQL DDL with multiple constraint types."""
    return """
    CREATE TABLE customers (
        customer_id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_email_nonempty CHECK (length(email) > 3)
    );

    CREATE TABLE orders (
        order_id BIGSERIAL PRIMARY KEY,
        customer_id INTEGER NOT NULL
            REFERENCES customers(customer_id) ON DELETE CASCADE,
        order_total NUMERIC(12, 2) NOT NULL,
        status VARCHAR(50) DEFAULT 'pending',
        ordered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_positive_total CHECK (order_total >= 0.0)
    );

    CREATE TABLE order_items (
        item_id BIGSERIAL PRIMARY KEY,
        order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
        sku VARCHAR(64) NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        unit_price NUMERIC(10, 2) NOT NULL,
        CONSTRAINT uq_order_sku UNIQUE (order_id, sku),
        CONSTRAINT chk_positive_qty CHECK (quantity > 0)
    );

    CREATE INDEX idx_orders_customer_status ON orders (customer_id, status);
    CREATE INDEX idx_order_items_sku ON order_items (sku);
    """
