#!/usr/bin/env bash
# Start the DEMO instance of Herald (docs/MEMORY_SAFETY.md §6). Unlike scripts/run_dev.sh there is no --reload: a
# file edit anywhere in the repo must never restart the server mid-demo. Whisper is preloaded (HERALD_STT_PRELOAD=1)
# so its memory is claimed before the demo starts and a failed load stops startup here, not on the first utterance.
# Refuses to start unless the memory guard is running and demo mode is on (HERALD_DEMO_SKIP_CHECKS=1 overrides).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
PORT="${PORT:-8100}"
STATUS="${HERALD_MEMGUARD_STATUS:-$HOME/.local/state/herald/memguard.json}"
FLAG="$HOME/.local/state/herald/demo_mode"
problems=()
systemctl --user is-active --quiet herald-memguard.service \
  || problems+=("memory guard service is not active: run scripts/memguard.sh install")
"$PY" -c "import json,sys,time; s=json.load(open(sys.argv[1])); sys.exit(0 if time.time()-s['ts']<5 else 1)" "$STATUS" \
  2>/dev/null || problems+=("memory guard heartbeat ($STATUS) is missing or stale: scripts/memguard.sh status")
[ -f "$FLAG" ] || problems+=("demo mode is off: run scripts/demo_mode.sh on")
if [ ${#problems[@]} -gt 0 ]; then
  printf 'run_demo: %s\n' "${problems[@]}" >&2
  if [ "${HERALD_DEMO_SKIP_CHECKS:-0}" = 1 ]; then
    echo "run_demo: WARNING: HERALD_DEMO_SKIP_CHECKS=1, starting anyway WITHOUT the memory safety net" >&2
  else
    exit 1
  fi
fi
export HERALD_STT_PRELOAD=1
echo "run_demo: Herald demo on :$PORT (no --reload, Whisper preloaded)"
exec "$PY" -m uvicorn herald.app:app --host "${HOST:-0.0.0.0}" --port "$PORT"
