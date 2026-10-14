"""Key=value structured logging.

One line per event, e.g.
2026-10-14T10:03:21.123Z level=INFO svc=gateway event=order_update req_id=ab12 status=FILLED

This format is deliberately easy to analyse with grep / awk / sed / cut,
which is exactly what you do in a support role.
"""
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.environ.get("TW_LOG_DIR", os.path.join(ROOT, "logs"))
os.makedirs(LOG_DIR, exist_ok=True)


class KV:
    def __init__(self, svc: str):
        self.svc = svc
        self.path = os.path.join(LOG_DIR, f"{svc}.log")

    def log(self, level: str, event: str, **kv):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        parts = [ts, f"level={level}", f"svc={self.svc}", f"event={event}"]
        for k, v in kv.items():
            if v is None:
                continue
            s = str(v)
            if " " in s or "=" in s or s == "":
                s = '"' + s.replace('"', "'") + '"'
            parts.append(f"{k}={s}")
        line = " ".join(parts)
        with open(self.path, "a") as f:
            f.write(line + "\n")
        print(line, file=sys.stdout, flush=True)

    def info(self, event, **kv):
        self.log("INFO", event, **kv)

    def warn(self, event, **kv):
        self.log("WARN", event, **kv)

    def error(self, event, **kv):
        self.log("ERROR", event, **kv)
