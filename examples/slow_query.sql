SELECT c.id, c.name, o.amount
FROM customers c, orders o
WHERE c.id = o.customer_id
  AND o.status = 'completed';
