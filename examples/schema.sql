CREATE TABLE customers (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    country VARCHAR(50) NOT NULL,
    is_vip BOOLEAN NOT NULL
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    amount NUMERIC NOT NULL,
    status VARCHAR(20) NOT NULL
);
