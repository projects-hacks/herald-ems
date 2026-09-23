#!/usr/bin/env bash
# Start the Herald server. PORT defaults to 8100; each teammate running their own copy should pick their own port.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
PORT="${PORT:-8100}"
exec "$PY" -m uvicorn herald.app:app --host 0.0.0.0 --port "$PORT" --reload --reload-dir herald --reload-dir web
