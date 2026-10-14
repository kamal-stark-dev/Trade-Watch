# TradeWatch: Order Flow Monitoring & Log Analysis

A small simulated trading platform for practising **application support** skills:
tracing orders across services, reading logs, writing SQL, spotting stale feeds,
handling incidents and writing post-mortems.

```
load_gen / client -> GATEWAY (8001) -> EXCHANGE SIM (8002)
                       |                    |  price feed (random walk, 4 futures: ES CL ZN GC)
                    SQLite orders           |  FIX-style execution reports
                       \__ logs/*.log (key=value, one line per event, shared req_id)

monitor/monitor.py  -> checks health, feed freshness, failures, latency; can auto-restart
scripts/chaos.py    -> injects failures (stale feed, slow exchange, reject-all, session down)
```

## 1. Setup (Linux / macOS / WSL on Windows)

```bash
cd tradewatch
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.          # run this in every new terminal, from the project root
bash scripts/service.sh start all
bash scripts/service.sh status all
```
Windows without WSL: run the two services manually in two terminals instead of service.sh:
`python -m uvicorn exchange_sim.main:app --port 8002` and `python -m uvicorn gateway.main:app --port 8001`.
(The Bash log tools need WSL or Git Bash; install WSL, it is also good Linux practice.)

## 2. Normal operation

```bash
python scripts/load_gen.py -n 100          # send random orders
curl localhost:8001/metrics                # status counts + latency, last 5 min
curl "localhost:8001/orders?limit=5"
curl localhost:8002/prices                 # price feed with age in seconds
python -m monitor.monitor --once           # exit code 0 = healthy
```

## 3. Log analysis (practise this daily)

```bash
bash scripts/log_queries.sh top-errors
bash scripts/log_queries.sh errors-per-minute
bash scripts/log_queries.sh rejects
bash scripts/log_queries.sh slowest
bash scripts/log_queries.sh trace <req_id>     # one order across gateway + exchange
tail -f logs/gateway.log | grep --line-buffered "level=ERROR"
```
Read the one-liners in `scripts/log_queries.sh`, then write 5 of your own
(e.g. rejects per symbol, orders per user per minute).

## 4. SQL

```bash
python scripts/run_sql.py sql/queries.sql
```
Edit `sql/queries.sql`; try writing "orders stuck for over 5 minutes" without looking.

## 5. Incident drills (the important part)

Run the monitor in one terminal: `python -m monitor.monitor` (add `--auto-restart` later).
In another terminal, break something, send load, then investigate **using only logs, SQL and the monitor**.

| Drill | Inject | What you should see | What to do |
|---|---|---|---|
| Stale prices | `python scripts/chaos.py freeze-feed` | `FEED_STALE` alert after about 10s | Confirm via `/prices` age_s, check exchange log, restart exchange per runbook |
| Slow exchange | `python scripts/chaos.py latency 3000` + load | gateway `exchange_timeout` errors, PENDING orders, `HIGH_LATENCY` | Do NOT resend. Reconcile: `curl -X POST localhost:8001/orders/<id>/reconcile` |
| Exchange down | `python scripts/chaos.py down` + load | `SEND_FAILED`, `EXCHANGE_DOWN`, 5xx from gateway | Scope impact, restart, verify, reconcile unknown orders |
| Reject storm | `python scripts/chaos.py reject-all` + load | spike of `Exchange rejecting all orders` | Distinguish from user errors (`rejects` query), escalate |
| User error | send an order with symbol `XX` | gateway `order_invalid`, HTTP 400 | Explain to user; not a system fault |

Reset anytime: `python scripts/chaos.py reset`.

For **each** drill write a short post-mortem (`docs/postmortem_template.md`) and keep the 2-3 best in `docs/`.

## 6. What to say in an interview

- Two FastAPI services with an order lifecycle (New, Acked, Filled/Partial, Rejected) and FIX-style execution reports.
- A shared request ID lets me trace one order across services in seconds.
- A timeout leaves the order in an **unknown** state: I reconcile with the exchange rather than resend (a resend could create a duplicate order).
- I separated user errors (invalid symbol at the gateway) from system errors (timeouts, session down).
- Monitoring: health checks, feed-staleness alerts, failure counts, auto-restart with a cooldown to avoid restart loops.
- Limits: simulated, synchronous, SQLite, no real FIX engine or sequence-number recovery.
  Next steps: a Grafana/Prometheus dashboard, real FIX sequence/resend handling, Dockerisation.

## Files

```
common/logsetup.py   key=value logger        common/fix.py      FIX-style build/parse
exchange_sim/main.py exchange + price feed   gateway/main.py    order gateway + SQLite
monitor/monitor.py   health/alert monitor    scripts/*          service.sh, load_gen, chaos, log_queries, run_sql
sql/queries.sql      support queries         docs/              runbook + post-mortem template
```
