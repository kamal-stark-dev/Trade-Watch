"""Exchange simulator (port 8002).

- Runs a price feed (random walk) for a few futures contracts.
- Accepts FIX-style new orders and answers with an execution report:
  rejected / acked-only / partially filled / filled.
- Has chaos switches so you can inject failures (see scripts/chaos.py).
"""
import asyncio
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from common import fix
from common.logsetup import KV

log = KV("exchange")

START = {"ES": 5400.00, "CL": 78.50, "ZN": 110.25, "GC": 2350.00}
TICK = {"ES": 0.25, "CL": 0.01, "ZN": 0.015625, "GC": 0.10}
BAND_PCT = 5.0  # orders priced more than 5% away from last price are rejected

prices = dict(START)
price_ts = {s: time.time() for s in START}
book = {}  # cl_ord_id -> latest known state (used for reconciliation)
chaos = {"feed_frozen": False, "latency_ms": 0, "reject_all": False, "down": False}


async def feed_loop():
    while True:
        if not chaos["feed_frozen"]:
            for s in prices:
                prices[s] = round(prices[s] + TICK[s] * random.randint(-3, 3), 6)
                price_ts[s] = time.time()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(feed_loop())
    log.info("exchange_started", symbols=",".join(START))
    yield
    task.cancel()


app = FastAPI(title="TradeWatch Exchange Simulator", lifespan=lifespan)


class FixIn(BaseModel):
    fix: str


@app.get("/health")
def health():
    if chaos["down"]:
        raise HTTPException(503, "exchange session down")
    return {"status": "ok"}


@app.get("/prices")
def get_prices():
    if chaos["down"]:
        raise HTTPException(503, "exchange session down")
    now = time.time()
    return {s: {"price": prices[s], "ts": price_ts[s], "age_s": round(now - price_ts[s], 1)}
            for s in prices}


@app.get("/chaos")
def get_chaos():
    return chaos


@app.post("/admin/chaos")
def set_chaos(body: dict):
    for k, v in body.items():
        if k in chaos:
            chaos[k] = v
    log.warn("chaos_changed", **{k: v for k, v in chaos.items()})
    return chaos


@app.get("/order/{cl_ord_id}")
def order_status(cl_ord_id: str):
    if chaos["down"]:
        raise HTTPException(503, "exchange session down")
    if cl_ord_id not in book:
        raise HTTPException(404, "unknown order")
    return book[cl_ord_id]


def _reject(cl_ord_id, order_id, sym, side, qty, reason, req_id):
    book[cl_ord_id] = {"status": "REJECTED", "reason": reason, "filled_qty": 0}
    log.warn("order_rejected", req_id=req_id, cl_ord_id=cl_ord_id, symbol=sym, reason=reason)
    return {"fix": fix.exec_report(cl_ord_id, order_id, sym, side, qty, "8", text=reason)}


@app.post("/order")
async def order(body: FixIn, x_request_id: str = Header(default="-")):
    if chaos["down"]:
        log.error("session_down", req_id=x_request_id)
        raise HTTPException(503, "exchange session down")

    log.info("order_in", req_id=x_request_id, fix=body.fix)
    if chaos["latency_ms"]:
        await asyncio.sleep(chaos["latency_ms"] / 1000)

    m = fix.parse(body.fix)
    cl, sym, side = m.get("11", "?"), m.get("55", "?"), m.get("54", "1")
    qty = int(m.get("38", "0"))
    px = float(m["44"]) if "44" in m else None
    order_id = "EXO-" + uuid.uuid4().hex[:8].upper()

    if sym not in prices:
        return _reject(cl, order_id, sym, side, qty, "Unknown symbol", x_request_id)
    if qty <= 0:
        return _reject(cl, order_id, sym, side, qty, "Invalid quantity", x_request_id)
    if chaos["reject_all"]:
        return _reject(cl, order_id, sym, side, qty, "Exchange rejecting all orders", x_request_id)
    last = prices[sym]
    if px is not None and abs(px - last) / last * 100 > BAND_PCT:
        return _reject(cl, order_id, sym, side, qty, "Price outside band", x_request_id)
    if random.random() < 0.08:
        return _reject(cl, order_id, sym, side, qty, "Risk limit exceeded", x_request_id)

    fill_px = px if px is not None else last
    r = random.random()
    if r < 0.70:      # filled
        status, last_qty, cum = "2", qty, qty
    elif r < 0.82:    # partial
        last_qty = max(1, qty // 2)
        status, cum = "1", last_qty
    else:             # acked only, never fills (will look "stuck")
        status, last_qty, cum = "0", 0, 0

    names = {"0": "ACKED", "1": "PARTIAL", "2": "FILLED"}
    book[cl] = {"status": names[status], "filled_qty": cum, "reason": None}
    log.info("order_out", req_id=x_request_id, cl_ord_id=cl, status=names[status], filled_qty=cum)
    return {"fix": fix.exec_report(cl, order_id, sym, side, qty, status,
                                   last_qty, fill_px if last_qty else None, cum)}
