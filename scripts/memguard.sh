#!/usr/bin/env bash
# Install / remove / inspect Herald's memory guard as a systemd --user service (docs/MEMORY_SAFETY.md).
#   scripts/memguard.sh install|uninstall|restart|status|logs [N]
# The service runs scripts/memguard.py with config/memguard.yaml, Restart=always; linger keeps it running without a
# login session and starts it at boot.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd -P)"
PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
UNIT=herald-memguard.service
UNIT_FILE="$HOME/.config/systemd/user/$UNIT"
STATE="$HOME/.local/state/herald"
case "${1:-status}" in
  install)
    mkdir -p "$(dirname "$UNIT_FILE")" "$STATE"
    "$PY" scripts/memguard.py once >/dev/null      # config loads and the probes work before we install
    cat > "$UNIT_FILE" <<UNITEOF
[Unit]
Description=Herald memory guard (docs/MEMORY_SAFETY.md)
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=$REPO
ExecStart=$PY $REPO/scripts/memguard.py run
Restart=always
RestartSec=2
LimitMEMLOCK=infinity
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
UNITEOF
    systemctl --user daemon-reload
    systemctl --user enable --now "$UNIT"
    loginctl enable-linger "$USER" 2>/dev/null || echo "note: loginctl enable-linger failed; the guard stops at logout"
    sleep 2; systemctl --user --no-pager status "$UNIT" | head -5
    "$PY" scripts/memguard.py status | head -12 ;;
  uninstall)
    systemctl --user disable --now "$UNIT" || true
    rm -f "$UNIT_FILE"; systemctl --user daemon-reload; echo "removed $UNIT" ;;
  restart) systemctl --user restart "$UNIT"; sleep 2; "$PY" scripts/memguard.py status | head -12 ;;
  status)
    systemctl --user --no-pager status "$UNIT" | head -5 || true
    "$PY" scripts/memguard.py status ;;
  logs) tail -n "${2:-30}" "$STATE/memguard.jsonl" ;;
  *) echo "usage: $0 install|uninstall|restart|status|logs [N]"; exit 2 ;;
esac
