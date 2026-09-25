#!/usr/bin/env bash
# Demo mode (docs/MEMORY_SAFETY.md §5): scripts/run_job.py refuses every job, the memory guard uses the demo
# thresholds and terminates any new non-protected process that holds GPU memory.
#   scripts/demo_mode.sh on|off|status
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
FLAG="$HOME/.local/state/herald/demo_mode"
guard_up() { systemctl --user is-active --quiet herald-memguard.service; }
case "${1:-status}" in
  on)
    mkdir -p "$(dirname "$FLAG")"; date -u +%FT%TZ > "$FLAG"
    echo "demo mode ON since $(cat "$FLAG")"
    guard_up || echo "WARNING: the memory guard is not running: scripts/memguard.sh install"
    echo "GPU holders right now (new non-protected ones will be terminated; existing ones below are yours to stop):"
    "$PY" scripts/memguard.py once | sed -n '/victims in kill order/,$p' ;;
  off) rm -f "$FLAG"; echo "demo mode OFF" ;;
  status)
    if [ -f "$FLAG" ]; then echo "demo mode ON since $(cat "$FLAG")"; else echo "demo mode OFF"; fi
    guard_up && echo "memory guard: running" || echo "memory guard: NOT running" ;;
  *) echo "usage: $0 on|off|status"; exit 2 ;;
esac
