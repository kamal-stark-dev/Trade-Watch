"""Tiny FIX-style helpers (simplified: '|' instead of SOH, no checksum).

Tags used:
 8=BeginString 35=MsgType(D=NewOrder, 8=ExecReport) 49=Sender 56=Target 52=SendingTime
 11=ClOrdID 37=OrderID 17=ExecID 55=Symbol 54=Side(1=Buy,2=Sell) 38=OrderQty
 40=OrdType(1=Market,2=Limit) 44=Price 39=OrdStatus 150=ExecType 32=LastQty 31=LastPx
 14=CumQty 151=LeavesQty 58=Text
OrdStatus(39): 0=New/Acked 1=PartiallyFilled 2=Filled 8=Rejected
"""
from datetime import datetime, timezone


def now_fix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H:%M:%S.%f")[:-3]


def build(fields) -> str:
    return "|".join(f"{t}={v}" for t, v in fields if v is not None)


def parse(msg: str) -> dict:
    out = {}
    for part in msg.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def new_order(cl_ord_id, symbol, side, qty, price=None) -> str:
    return build([
        ("8", "FIX.4.2"), ("35", "D"), ("49", "TWGATEWAY"), ("56", "EXCHSIM"),
        ("52", now_fix()), ("11", cl_ord_id), ("55", symbol),
        ("54", "1" if side == "BUY" else "2"), ("38", qty),
        ("40", "2" if price is not None else "1"), ("44", price),
    ])


def exec_report(cl_ord_id, order_id, symbol, side_tag, qty, ord_status,
                last_qty=0, last_px=None, cum_qty=0, text=None) -> str:
    return build([
        ("8", "FIX.4.2"), ("35", "8"), ("49", "EXCHSIM"), ("56", "TWGATEWAY"),
        ("52", now_fix()), ("11", cl_ord_id), ("37", order_id),
        ("17", "EX" + order_id[-6:]), ("150", ord_status), ("39", ord_status),
        ("55", symbol), ("54", side_tag), ("38", qty), ("32", last_qty),
        ("31", last_px), ("14", cum_qty), ("151", int(qty) - int(cum_qty)),
        ("58", text),
    ])
