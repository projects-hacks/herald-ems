#!/usr/bin/env bash
# Protocol-update demo with real documents: install the previous 700-S04 (effective Jan 1 2025), serve the current
# one (effective Jan 1 2026) from a local mirror, and let Herald's sync pick it up on a good link.
#   scripts/demo_protocol_update.sh setup    # installs the old version, starts the mirror on :8300
#   then run Herald with HERALD_PROTOCOL_MIRROR=http://127.0.0.1:8300, switch the link to good (Shift+G),
#   and watch GET /api/protocols: 700-S04 becomes review_required with the new effective date.
#   scripts/demo_protocol_update.sh reset    # back to the reviewed files
set -euo pipefail
cd "$(dirname "$0")/.."
D=data/protocols/santa_clara
case "${1:-}" in
  setup)
    mkdir -p "$D/versions" data/protocols/demo_mirror/santa_clara
    cp "$D/archive/previous/700-S04_routine-medical-care-adult_eff-2025-01-01.pdf" "$D/versions/700-S04_previous.pdf"
    printf '{"700-S04": {"file": "versions/700-S04_previous.pdf", "review_required": false}}\n' > "$D/manifest.json"
    cp "$D/archive/700-S04_routine-medical-care-adult_eff-2026-01-01.pdf" data/protocols/demo_mirror/santa_clara/700-S04.pdf
    nohup ~/miniforge3/envs/zgx/bin/python scripts/protocol_mirror.py data/protocols/demo_mirror --port 8300 >/dev/null 2>&1 &
    echo "installed 700-S04 (effective Jan 1 2025); mirror serving the Jan 1 2026 version on :8300 (pid $!)" ;;
  reset)
    rm -f "$D/manifest.json"; rm -rf "$D/versions" data/protocols/demo_mirror
    pkill -f "^/home/hp18/miniforge3/envs/zgx/bin/python scripts/protocol_mirror.py" || true
    echo "reset to the reviewed files" ;;
  *) echo "usage: $0 setup|reset"; exit 1 ;;
esac
