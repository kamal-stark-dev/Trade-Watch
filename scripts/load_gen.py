"""Send random orders to the gateway.   python scripts/load_gen.py -n 100 --delay 0.05"""
import argparse
import random
import time
from collections import Counter

import httpx

GW = "http://127.0.0.1:8001"
EX = "http://127.0.0.1:8002"
USERS = ["alice", "bob", "carol", "dave", "erin"]
SYMBOLS = ["ES", "CL", "ZN", "GC"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--delay", type=float, default=0.05)
    a = ap.parse_args()

    try:
        px = {s: v["price"] for s, v in httpx.get(f"{EX}/prices", timeout=2).json().items()}
    except Exception:
        px = {"ES": 5400, "CL": 78.5, "ZN": 110.25, "GC": 2350}

    results = Counter()
    for _ in range(a.n):
        r = random.random()
        sym = "XX" if r < 0.04 else random.choice(SYMBOLS)   # 4% user typos
        base = px.get(sym, 100)
        k = random.random()
        if k < 0.60:
            price = round(base * (1 + random.uniform(-0.002, 0.002)), 2)   # limit near market
        elif k < 0.70:
            price = round(base * (1 + random.choice([-1, 1]) * 0.08), 2)   # far off: price band reject
        else:
            price = None                                                  # market order
        body = {"user": random.choice(USERS), "symbol": sym, "side": random.choice(["BUY", "SELL"]),
                "qty": random.randint(1, 50), "price": price}
        try:
            resp = httpx.post(f"{GW}/orders", json=body, timeout=10)
            results[resp.json().get("status", f"HTTP {resp.status_code}")] += 1
        except Exception as e:
            results[f"CLIENT_ERROR:{type(e).__name__}"] += 1
        time.sleep(a.delay)

    print("Results:", dict(results))


if __name__ == "__main__":
    main()
