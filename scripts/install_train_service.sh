#!/usr/bin/env bash
# Install (and optionally start) the run F training supervisor as a systemd --user service.
#   scripts/install_train_service.sh           # install + enable: starts at the next boot, not now
#   scripts/install_train_service.sh --start   # install + enable + start now (this starts the real 30B run)
#   scripts/install_train_service.sh --remove  # stop, disable, uninstall
# Status: systemctl --user status herald-train ; log: runs/herald-f-train.log ; journalctl --user -u herald-train
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
unit=herald-train.service
dest="$HOME/.config/systemd/user"
if [ "${1:-}" = --remove ]; then
  systemctl --user disable --now "$unit" 2>/dev/null || true
  rm -f "$dest/$unit"; systemctl --user daemon-reload; echo "removed $unit"; exit 0
fi
loginctl show-user "$USER" -p Linger | grep -q 'Linger=yes' || echo "warning: linger is off; the service won't start after a reboot until someone logs in (loginctl enable-linger $USER needs admin)"
mkdir -p "$dest"
install -m 644 "$here/systemd/$unit" "$dest/$unit"
systemctl --user daemon-reload
systemctl --user enable "$unit"
if [ "${1:-}" = --start ]; then systemctl --user start "$unit"; echo "started $unit"; else echo "enabled $unit (not started; --start starts it)"; fi
