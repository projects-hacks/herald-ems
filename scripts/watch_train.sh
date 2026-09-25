#!/usr/bin/env bash
# Heartbeat for a long training run, so a stall is visible without waiting on a blocking command.
# Appends one line every --every seconds: the newest optimizer step and loss, the weight-load progress while the
# model is still loading, MemAvailable, this job's GPU memory, the memory guard's level, and whether the job is
# still alive. A step number that stops moving while the timestamps keep advancing means it is stuck.
#
#   scripts/watch_train.sh <run-dir> [job-log] [--every N]        # e.g. runs/herald-f-smoke runs/smoke_f.log
#   tail -f runs/<run-dir>/watch.log
set -uo pipefail
RUN="${1:?run dir, e.g. runs/herald-f-smoke}"
JOBLOG="${2:-}"
EVERY=30
[ "${3:-}" = "--every" ] && EVERY="${4:-30}"
OUT="$RUN/watch.log"
mkdir -p "$RUN"

last_step=""
stalled=0
while true; do
  now=$(date -u '+%H:%M:%S')
  # newest step / loss / epoch from the trainer's own log
  read -r step loss ep < <(python3 - "$RUN/log.jsonl" <<'PY' 2>/dev/null || echo "- - -"
import json,sys
try:
    rows=[json.loads(l) for l in open(sys.argv[1]) if l.strip().startswith('{')]
except Exception:
    rows=[]
if rows:
    r=rows[-1]
    print(r.get('step','-'), round(r.get('loss',0),4), round(r.get('epoch',0),3))
else:
    print('- - -')
PY
)
  avail=$(awk '/MemAvailable/{printf "%.1f", $2/1048576}' /proc/meminfo)
  gpu=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null | sort -rn | head -1)
  lvl=$(python3 -c "
import json
try: print(json.load(open('$HOME/.local/state/herald/memguard.json'))['level'])
except Exception: print('?')" 2>/dev/null)
  alive=$(systemctl --user list-units 'herald-job-*' --no-pager 2>/dev/null | grep -c 'herald-job-.*running' || true)
  # Not every trainer writes log.jsonl (scripts/train_lora.py reports through tqdm), so fall back to the job log:
  # the tqdm step counter while training, or the weight-loader's counter before the first step.
  extra=""
  if [ "$step" = "-" ] && [ -n "$JOBLOG" ] && [ -f "$JOBLOG" ]; then
    tq=$(tr '\r' '\n' < "$JOBLOG" | grep -oE '[0-9]+/[0-9]+ \[[0-9:]+<[0-9:]+, +[0-9.]+s/it' | tail -1)
    if [ -n "$tq" ]; then
      step="${tq%% *}"                                  # e.g. 39/868
      extra=" rate=$(printf '%s' "$tq" | grep -oE '[0-9.]+s/it$')"
    else
      extra=" load=$(tr '\r' '\n' < "$JOBLOG" | grep -o 'Loading weights: *[0-9]*%[^|]*| *[0-9]*/[0-9]*' | tail -1 | grep -o '[0-9]*/[0-9]*$')"
    fi
    lo=$(tr '\r' '\n' < "$JOBLOG" | grep -o "'loss': '[0-9.e+-]*'" | tail -1 | grep -oE "[0-9.e+-]+$")
    [ -n "$lo" ] && loss="$lo"
  fi
  # stall detection: same step for 10 consecutive ticks
  if [ "$step" = "$last_step" ]; then stalled=$((stalled+1)); else stalled=0; last_step="$step"; fi
  warn=""
  [ "$stalled" -ge 10 ] && warn="  <-- STEP UNCHANGED for $((stalled*EVERY))s"
  printf '%s step=%s loss=%s epoch=%s avail=%sGiB gpu=%sMiB guard=%s jobs=%s%s%s\n' \
    "$now" "$step" "$loss" "$ep" "$avail" "${gpu:-0}" "$lvl" "$alive" "$extra" "$warn" >> "$OUT"
  # stop once the job is gone and a terminal marker exists
  if [ "$alive" = "0" ] && { [ -f "$RUN/DONE" ] || [ -f "$RUN/report.json" ]; }; then
    printf '%s watcher exiting: job gone, run has a terminal marker\n' "$now" >> "$OUT"; exit 0
  fi
  sleep "$EVERY"
done
