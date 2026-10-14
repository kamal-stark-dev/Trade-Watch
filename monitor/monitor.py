"""Health monitor. Checks gateway, exchange, price-feed freshness and recent failures.

Usage:
  python -m monitor.monitor                 # check every 5s, print/log alerts
  python -m monitor.monitor --once          # single check, exit code 1 if any alert
  python -m monitor.monitor --auto-restart  # also restart failed services via scripts/service.sh
"""
import argparse
import os
import subprocess
import sys
import time

import httpx

from common.logsetup import KV, ROOT

log = KV("monitor")
GW = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8001")
EX = os.environ.get("EXCHANGE_URL", "http://127.0.0.1:8002")
SERVICE_SH = os.path.join(ROOT, "scripts", "service.sh")
last_restart = {}


def get(url, timeout=2):
    try:
        return httpx.get(url, timeout=timeout)
    except httpx.HTTPError:
        return None


def check(stale_after, max_failures, max_latency_ms):
    alerts = []  # (alert_name, service_to_restart_or_None, detail)

    r = get(f"{GW}/health")
    if r is None or r.status_code != 200:
        alerts.append(("GATEWAY_DOWN", "gateway", "health check failed"))

    r = get(f"{EX}/health")
    if r is None or r.status_code != 200:
        alerts.append(("EXCHANGE_DOWN", "exchange", "health check failed"))
    else:
        p = get(f"{EX}/prices")
        if p is not None and p.status_code == 200:
            ages = {s: v["age_s"] for s, v in p.json().items()}
            worst = max(ages.values())
            if worst > stale_after:
                alerts.append(("FEED_STALE", "exchange", f"oldest price {worst}s old (limit {stale_after}s)"))

    m = get(f"{GW}/metrics?window_min=1")
    if m is not None and m.status_code == 200:
        d = m.json()
        bad = d["by_status"].get("PENDING", 0) + d["by_status"].get("SEND_FAILED", 0)
        if bad >= max_failures:
            alerts.append(("ORDER_FAILURES", None, f"{bad} PENDING/SEND_FAILED orders in last 1 min"))
        if d["avg_latency_ms"] and d["avg_latency_ms"] > max_latency_ms:
            alerts.append(("HIGH_LATENCY", None, f"avg order latency {d['avg_latency_ms']}ms"))
    return alerts


def restart(service):
    now = time.time()
    if now - last_restart.get(service, 0) < 30:  # cooldown, avoid restart loops
        log.warn("restart_skipped", service=service, reason="cooldown")
        return
    last_restart[service] = now
    log.warn("restart_attempt", service=service)
    subprocess.run(["bash", SERVICE_SH, "restart", service], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--auto-restart", action="store_true")
    ap.add_argument("--stale-after", type=float, default=10)
    ap.add_argument("--max-failures", type=int, default=3)
    ap.add_argument("--max-latency-ms", type=float, default=1000)
    a = ap.parse_args()

    while True:
        alerts = check(a.stale_after, a.max_failures, a.max_latency_ms)
        if not alerts:
            log.info("check_ok")
        for name, svc, detail in alerts:
            log.error("alert", name=name, detail=detail)
            if a.auto_restart and svc:
                restart(svc)
        if a.once:
            sys.exit(1 if alerts else 0)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
