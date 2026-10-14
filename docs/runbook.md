# Runbook (L1/L2)

General flow: **Clarify -> scope impact -> isolate the layer -> check logs/metrics -> fix or escalate -> communicate -> document.**

## A. FEED_STALE (prices not updating)
1. Confirm: `curl localhost:8002/prices` -> check `age_s` per symbol. All symbols or one?
2. Check `logs/exchange.log` for `chaos_changed`/errors and whether the exchange process is alive (`scripts/service.sh status all`).
3. Fix: `scripts/service.sh restart exchange` (only after noting the time and informing users).
4. Verify: ages drop below 2s; `python -m monitor.monitor --once` returns 0.
5. Communicate: impact window, affected symbols, next update time.

## B. Orders PENDING / exchange_timeout
1. Scope: `curl "localhost:8001/orders?status=PENDING"`; check `bash scripts/log_queries.sh top-errors`.
2. Do **not** resend. The exchange may have processed the order.
3. After the exchange recovers, reconcile each: `curl -X POST localhost:8001/orders/<order_id>/reconcile`.
4. Tell affected users the real outcome of each order.

## C. EXCHANGE_DOWN / SEND_FAILED
1. Confirm via `/health` and `logs/gateway.log` (`exchange_unreachable` / `exchange_error`).
2. Restart exchange, verify health, then reconcile SEND_FAILED/PENDING orders.
3. Escalate to L3/infra if the restart does not fix it or it recurs.

## D. Reject storm
1. `bash scripts/log_queries.sh rejects`: one reason dominating?
2. If reason is user-side (invalid symbol, price band): guide users. If it's exchange-side (all orders rejected): escalate with timestamps and sample req_ids.

## Escalation message template
Impact: <who/what/since when> | Evidence: <req_ids, log lines, query output> | Done so far: <steps> | Ask: <what you need from them>
