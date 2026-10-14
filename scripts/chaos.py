"""Inject failures into the exchange simulator.

  python scripts/chaos.py freeze-feed     # price feed stops updating (stale prices)
  python scripts/chaos.py latency 3000    # exchange takes 3s to answer (gateway times out at 2s)
  python scripts/chaos.py reject-all      # exchange rejects every order
  python scripts/chaos.py down            # exchange session down (HTTP 503)
  python scripts/chaos.py reset           # back to normal
  python scripts/chaos.py show
"""
import sys

import httpx

EX = "http://127.0.0.1:8002"
RESET = {"feed_frozen": False, "latency_ms": 0, "reject_all": False, "down": False}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    body = {
        "freeze-feed": {"feed_frozen": True},
        "latency": {"latency_ms": int(sys.argv[2]) if len(sys.argv) > 2 else 3000},
        "reject-all": {"reject_all": True},
        "down": {"down": True},
        "reset": RESET,
        "show": None,
    }.get(cmd, "bad")
    if body == "bad":
        print(__doc__)
        sys.exit(2)
    try:
        r = httpx.post(f"{EX}/admin/chaos", json=body, timeout=3) if body else httpx.get(f"{EX}/chaos", timeout=3)
    except httpx.HTTPError as e:
        print(f"Cannot reach the exchange simulator ({type(e).__name__}). Is it running? scripts/service.sh status all")
        sys.exit(1)
    print(r.json())


if __name__ == "__main__":
    main()
