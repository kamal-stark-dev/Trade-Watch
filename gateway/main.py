"""Order gateway (port 8001).

Flow: client -> gateway (validate, store in SQLite, log) -> exchange simulator -> execution report -> update DB.
Every request carries a request ID (req_id) that appears in the gateway AND exchange logs,
so you can trace one order across services with:  grep req_id=<id> logs/*.log
"""
import os
import sqlite3
import time
import uuid
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from common import fix
from common.logsetup import KV, ROOT

log = KV("gateway")
EXCHANGE_URL = os.environ.get("EXCHANGE_URL", "http://127.0.0.1:8002")
DB_PATH = os.environ.get("TW_DB", os.path.join(ROOT, "data", "tradewatch.db"))
EXCHANGE_TIMEOUT_S = float(os.environ.get("EXCHANGE_TIMEOUT_S", "2.0"))
VALID_SYMBOLS = {"ES", "CL", "ZN", "GC"}
STATUS_MAP = {"0": "ACKED", "1": "PARTIAL", "2": "FILLED", "8": "REJECTED"}

app = FastAPI(title="TradeWatch Order Gateway")


def run(sql, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        return rows
    finally:
        conn.close()


run("""CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    req_id TEXT,
    user TEXT,
    symbol TEXT,
    side TEXT,
    qty INTEGER,
    price REAL,
    status TEXT,
    reject_reason TEXT,
    filled_qty INTEGER DEFAULT 0,
    latency_ms REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)""")


class OrderIn(BaseModel):
    user: str
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: int = Field(gt=0)
    price: Optional[float] = None  # None = market order


def _update(order_id, **fields):
    sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=CURRENT_TIMESTAMP"
    run(f"UPDATE orders SET {sets} WHERE order_id=?", (*fields.values(), order_id))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics(window_min: int = 5):
    w = f"-{window_min} minutes"
    by = run("SELECT status, COUNT(*) AS c FROM orders WHERE created_at >= datetime('now', ?) GROUP BY status", (w,))
    lat = run("SELECT AVG(latency_ms) AS a FROM orders WHERE created_at >= datetime('now', ?) AND latency_ms IS NOT NULL", (w,))
    return {"window_min": window_min,
            "by_status": {r["status"]: r["c"] for r in by},
            "avg_latency_ms": round(lat[0]["a"], 1) if lat[0]["a"] is not None else None}


@app.get("/orders")
def list_orders(limit: int = 20, status: Optional[str] = None):
    if status:
        return run("SELECT * FROM orders WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
    return run("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    rows = run("SELECT * FROM orders WHERE order_id=?", (order_id,))
    return rows[0] if rows else JSONResponse({"error": "not found"}, status_code=404)


@app.post("/orders")
def create_order(o: OrderIn, x_request_id: Optional[str] = Header(default=None)):
    req_id = x_request_id or uuid.uuid4().hex[:12]
    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    t0 = time.time()
    log.info("order_received", req_id=req_id, order_id=order_id, user=o.user,
             symbol=o.symbol, side=o.side, qty=o.qty, price=o.price)

    # User error: caught at the gateway, never reaches the exchange
    if o.symbol not in VALID_SYMBOLS:
        run("INSERT INTO orders (order_id, req_id, user, symbol, side, qty, price, status, reject_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (order_id, req_id, o.user, o.symbol, o.side, o.qty, o.price, "REJECTED", "Invalid symbol (gateway)"))
        log.warn("order_invalid", req_id=req_id, order_id=order_id, symbol=o.symbol, source="gateway")
        return JSONResponse({"order_id": order_id, "req_id": req_id, "status": "REJECTED",
                             "reason": "Invalid symbol (gateway)"}, status_code=400)

    run("INSERT INTO orders (order_id, req_id, user, symbol, side, qty, price, status) VALUES (?,?,?,?,?,?,?,?)",
        (order_id, req_id, o.user, o.symbol, o.side, o.qty, o.price, "NEW"))

    msg = fix.new_order(order_id, o.symbol, o.side, o.qty, o.price)
    log.info("order_sent", req_id=req_id, order_id=order_id, fix=msg)

    try:
        r = httpx.post(f"{EXCHANGE_URL}/order", json={"fix": msg},
                       headers={"x-request-id": req_id}, timeout=EXCHANGE_TIMEOUT_S)
    except httpx.TimeoutException:
        ms = round((time.time() - t0) * 1000, 1)
        _update(order_id, status="PENDING", latency_ms=ms)
        log.error("exchange_timeout", req_id=req_id, order_id=order_id, latency_ms=ms,
                  note="order state UNKNOWN - do not resend blindly, reconcile")
        return JSONResponse({"order_id": order_id, "req_id": req_id, "status": "PENDING",
                             "reason": "exchange timeout"}, status_code=504)
    except httpx.HTTPError as e:
        ms = round((time.time() - t0) * 1000, 1)
        _update(order_id, status="SEND_FAILED", latency_ms=ms)
        log.error("exchange_unreachable", req_id=req_id, order_id=order_id, error=type(e).__name__)
        return JSONResponse({"order_id": order_id, "req_id": req_id, "status": "SEND_FAILED",
                             "reason": "exchange unreachable"}, status_code=502)

    ms = round((time.time() - t0) * 1000, 1)
    if r.status_code != 200:
        _update(order_id, status="SEND_FAILED", latency_ms=ms)
        log.error("exchange_error", req_id=req_id, order_id=order_id, http_status=r.status_code)
        return JSONResponse({"order_id": order_id, "req_id": req_id, "status": "SEND_FAILED",
                             "reason": f"exchange HTTP {r.status_code}"}, status_code=503)

    er = fix.parse(r.json()["fix"])
    status = STATUS_MAP.get(er.get("39"), "UNKNOWN")
    reason = er.get("58")
    filled = int(er.get("14", "0"))
    _update(order_id, status=status, reject_reason=reason, filled_qty=filled, latency_ms=ms)
    if status == "REJECTED":
        log.warn("order_update", req_id=req_id, order_id=order_id, status=status, reason=reason, latency_ms=ms)
    else:
        log.info("order_update", req_id=req_id, order_id=order_id, status=status, filled_qty=filled, latency_ms=ms)
    return {"order_id": order_id, "req_id": req_id, "status": status,
            "filled_qty": filled, "reason": reason, "latency_ms": ms}


@app.post("/orders/{order_id}/reconcile")
def reconcile(order_id: str):
    """For orders in unknown state (PENDING): ask the exchange what it knows instead of resending."""
    rows = run("SELECT * FROM orders WHERE order_id=?", (order_id,))
    if not rows:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        r = httpx.get(f"{EXCHANGE_URL}/order/{order_id}", timeout=EXCHANGE_TIMEOUT_S)
    except httpx.HTTPError as e:
        log.error("reconcile_failed", order_id=order_id, error=type(e).__name__)
        return JSONResponse({"error": "exchange unreachable"}, status_code=502)
    if r.status_code == 404:
        _update(order_id, status="NOT_AT_EXCHANGE")
        log.warn("reconcile_result", order_id=order_id, result="NOT_AT_EXCHANGE")
        return {"order_id": order_id, "status": "NOT_AT_EXCHANGE"}
    if r.status_code != 200:
        return JSONResponse({"error": f"exchange HTTP {r.status_code}"}, status_code=503)
    ex = r.json()
    _update(order_id, status=ex["status"], filled_qty=ex.get("filled_qty", 0), reject_reason=ex.get("reason"))
    log.info("reconcile_result", order_id=order_id, result=ex["status"])
    return {"order_id": order_id, "status": ex["status"], "filled_qty": ex.get("filled_qty", 0)}
