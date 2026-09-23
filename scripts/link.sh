#!/usr/bin/env bash
# Emulated ED link for the demo (userspace, no root).
#   scripts/link.sh start <ed_host:port>   start Toxiproxy and create ed_link on :9000 -> ED receiver
#   scripts/link.sh good|weak|down         switch the link (same as the presenter hotkeys)
# Then run Herald with HERALD_ED_URL=http://127.0.0.1:9000
set -euo pipefail
BIN="$HOME/.local/bin"
case "${1:-}" in
  start)
    pgrep -f "toxiproxy-server -host" >/dev/null || (setsid nohup "$BIN/toxiproxy-server" -host 127.0.0.1 -port 8474 >/tmp/toxiproxy.log 2>&1 &)
    sleep 1
    "$BIN/toxiproxy-cli" create -l 0.0.0.0:9000 -u "${2:?ed host:port}" ed_link 2>/dev/null || true
    "$BIN/toxiproxy-cli" list ;;
  good|weak|down)
    curl -s -X POST "http://localhost:${PORT:-8100}/api/netem/$1"; echo ;;
  *) echo "usage: $0 start <ed_host:port> | good | weak | down"; exit 1 ;;
esac
