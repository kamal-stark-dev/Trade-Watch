-- 1. Order count by status
SELECT status, COUNT(*) AS orders FROM orders GROUP BY status ORDER BY orders DESC;

-- 2. Rejected orders per user
SELECT user, COUNT(*) AS rejected FROM orders WHERE status = 'REJECTED' GROUP BY user ORDER BY rejected DESC;

-- 3. Reject reasons (user error vs exchange/system reason)
SELECT reject_reason, COUNT(*) AS n FROM orders WHERE status = 'REJECTED' GROUP BY reject_reason ORDER BY n DESC;

-- 4. Stuck orders: still NEW / PENDING / ACKED after 5 minutes (change the interval to test quickly)
SELECT order_id, user, symbol, status, created_at FROM orders
WHERE status IN ('NEW', 'PENDING', 'ACKED') AND created_at < datetime('now', '-5 minutes')
ORDER BY created_at;

-- 5. Orders in unknown state (gateway timeout or send failure)
SELECT order_id, user, symbol, status, latency_ms, created_at FROM orders
WHERE status IN ('PENDING', 'SEND_FAILED') ORDER BY created_at DESC LIMIT 20;

-- 6. Filled volume per symbol
SELECT symbol, SUM(filled_qty) AS filled_qty, COUNT(*) AS orders FROM orders
WHERE status IN ('FILLED', 'PARTIAL') GROUP BY symbol ORDER BY filled_qty DESC;

-- 7. Average latency per symbol (ms)
SELECT symbol, ROUND(AVG(latency_ms), 1) AS avg_ms, MAX(latency_ms) AS max_ms FROM orders
WHERE latency_ms IS NOT NULL GROUP BY symbol ORDER BY avg_ms DESC;

-- 8. Orders per minute (spot spikes or gaps)
SELECT strftime('%Y-%m-%d %H:%M', created_at) AS minute, COUNT(*) AS orders FROM orders
GROUP BY minute ORDER BY minute DESC LIMIT 15;

-- 9. 10 slowest orders
SELECT order_id, user, symbol, status, latency_ms FROM orders
WHERE latency_ms IS NOT NULL ORDER BY latency_ms DESC LIMIT 10
