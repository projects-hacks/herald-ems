#!/usr/bin/env bash
# Start the Herald server. PORT defaults to 8100; each teammate running their own copy should pick their own port.
#
# Binds to 127.0.0.1 by default (B7): only this box can reach it. The tablet in the back of the ambulance is a
# separate device on the LAN, so a real run needs HERALD_BIND_HOST=0.0.0.0 (every interface) -- do that only on
# a network you trust, and set HERALD_DEVICE_TOKEN too (herald/config/settings.py), or any other device on that
# LAN/Wi-Fi can read and write patient state:
#   HERALD_BIND_HOST=0.0.0.0 HERALD_DEVICE_TOKEN=<shared secret> PORT=8101 scripts/run_dev.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
PORT="${PORT:-8100}"
HOST="${HERALD_BIND_HOST:-127.0.0.1}"
exec "$PY" -m uvicorn herald.app:app --host "$HOST" --port "$PORT" --reload --reload-dir herald --reload-dir web
