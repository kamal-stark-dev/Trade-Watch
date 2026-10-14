#!/usr/bin/env bash
# Start/stop/restart/status for the TradeWatch services.
# usage: scripts/service.sh {start|stop|restart|status} {exchange|gateway|all}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run"; LOGS="$ROOT/logs"
mkdir -p "$RUN" "$LOGS"
PY="${PYTHON:-python3}"
cd "$ROOT" || exit 1

app_of()  { case "$1" in exchange) echo "exchange_sim.main:app";; gateway) echo "gateway.main:app";; esac; }
port_of() { case "$1" in exchange) echo 8002;; gateway) echo 8001;; esac; }

is_running() {
  local pidfile="$RUN/$1.pid"
  [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

start_one() {
  if is_running "$1"; then echo "$1 already running (pid $(cat "$RUN/$1.pid"))"; return; fi
  nohup "$PY" -m uvicorn "$(app_of "$1")" --host 127.0.0.1 --port "$(port_of "$1")" \
        >> "$LOGS/$1.out" 2>&1 &
  echo $! > "$RUN/$1.pid"
  for _ in $(seq 1 20); do
    curl -s -o /dev/null "http://127.0.0.1:$(port_of "$1")/health" && { echo "$1 started (pid $(cat "$RUN/$1.pid"), port $(port_of "$1"))"; return; }
    sleep 0.25
  done
  echo "$1 did not become healthy - check logs/$1.out"
}

stop_one() {
  if is_running "$1"; then
    kill "$(cat "$RUN/$1.pid")" && echo "$1 stopped"
    sleep 0.5
  else
    echo "$1 not running"
  fi
  rm -f "$RUN/$1.pid"
}

status_one() {
  if is_running "$1"; then echo "$1: RUNNING (pid $(cat "$RUN/$1.pid"))"; else echo "$1: STOPPED"; fi
}

act="$1"; target="${2:-all}"
[[ "$target" == "all" ]] && targets="exchange gateway" || targets="$target"

case "$act" in
  start)   for t in $targets; do start_one "$t"; done ;;
  stop)    for t in $(echo $targets | tr ' ' '\n' | tac); do stop_one "$t"; done ;;
  restart) for t in $targets; do stop_one "$t"; start_one "$t"; done ;;
  status)  for t in $targets; do status_one "$t"; done ;;
  *) echo "usage: $0 {start|stop|restart|status} {exchange|gateway|all}"; exit 2 ;;
esac
