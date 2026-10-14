#!/usr/bin/env bash
# Log analysis one-liners (grep / awk / sed / sort / uniq). Read them, then try writing your own.
# usage: scripts/log_queries.sh <command> [arg]
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
L="$ROOT/logs"

case "$1" in
  top-errors)        # most frequent ERROR events
    grep -h "level=ERROR" "$L"/*.log | sed -E 's/.*event=([a-z_]+).*/\1/' | sort | uniq -c | sort -rn | head -10 ;;
  errors-per-minute) # error spikes: first 16 chars of timestamp = YYYY-MM-DDTHH:MM
    grep -h "level=ERROR" "$L"/*.log | cut -c1-16 | sort | uniq -c ;;
  warn-or-error)     # everything not INFO, by service and event
    grep -hE "level=(WARN|ERROR)" "$L"/*.log | awk '{print $3, $4}' | sort | uniq -c | sort -rn ;;
  rejects)           # reject reasons, most common first
    grep -h "event=order_update" "$L/gateway.log" | grep "status=REJECTED" \
      | sed -E 's/.*reason=("[^"]*"|[^ ]+).*/\1/' | sort | uniq -c | sort -rn ;;
  slowest)           # 10 slowest orders by latency_ms
    grep -h "event=order_update" "$L/gateway.log" \
      | awk '{for(i=1;i<=NF;i++) if($i ~ /^latency_ms=/){split($i,a,"="); print a[2], $0}}' \
      | sort -rn | head -10 | cut -c1-200 ;;
  orders-per-user)
    grep -h "event=order_received" "$L/gateway.log" \
      | awk '{for(i=1;i<=NF;i++) if($i ~ /^user=/){split($i,a,"="); print a[2]}}' | sort | uniq -c | sort -rn ;;
  trace)             # follow ONE request across services: scripts/log_queries.sh trace <req_id>
    [[ -z "$2" ]] && { echo "usage: $0 trace <req_id>"; exit 2; }
    grep -h "req_id=$2" "$L"/*.log | sort ;;
  first-error)       # when did trouble start? first ERROR line
    grep -h "level=ERROR" "$L"/*.log | sort | head -1 ;;
  *)
    echo "commands: top-errors errors-per-minute warn-or-error rejects slowest orders-per-user trace <req_id> first-error"
    exit 2 ;;
esac
