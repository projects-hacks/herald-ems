#!/usr/bin/env bash
# One command for the whole Herald system on the ZGX Nano (bare metal; Docker is only the clean-clone rebuild path).
#
#   scripts/herald.sh up        start everything that is not already running, verify it, print the URLs
#   scripts/herald.sh status    what is running and whether it is healthy
#   scripts/herald.sh logs      follow the app, ED screen and link-emulator logs
#   scripts/herald.sh down      stop the app, ED screen and link emulator started here (models keep serving)
#
# `up` does, in order, and skips any step that is already done:
#   1. checks this checkout against origin/main (warns if it is behind; `up --pull` fast-forwards first)
#   2. one-time data: the RxNorm drug index (~10 min, network) and the Whisper + embedding weights
#   3. the shipped model stack on ZRT :8080 -- ems-e-v2-fp8 (speech -> facts) and herald-f (photos, the monitor,
#      protocol figures and reranking) -- served one at a time, each only if missing and only if memory allows.
#      The untuned qwen3vl-fp8 is the baseline and the rollback: HERALD_VISION_MODEL=qwen3vl-fp8 switches back.
#   4. the React UI build (npm ci / npm run build only when sources changed)
#   5. the ED link emulator (Toxiproxy :9000 -> ED screen) and the ED screen (:8200)
#   6. the Herald app (:8100) with Whisper preloaded, then waits until speech, extraction and vision all report ready
#
# Overrides: HERALD_PORT (8100) ED_PORT (8200) HERALD_LLM_MODEL (ems-e-v2-fp8) HERALD_VISION_MODEL (herald-f)
#            HERALD_BIND_HOST (127.0.0.1; 0.0.0.0 exposes the app to the LAN -- set HERALD_DEVICE_TOKEN too)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
NODE_BIN="${HERALD_NODE_BIN:-$HOME/miniforge3/envs/herald-ui/bin}"
TOXI="$HOME/.local/bin"
PORT="${HERALD_PORT:-8100}"
ED_PORT="${ED_PORT:-8200}"
LINK_PORT=9000
LLM="${HERALD_LLM_MODEL:-ems-e-v2-fp8}"
VISION="${HERALD_VISION_MODEL:-herald-f}"   # the shipping vision model (photos, monitor, figures, reranking)
ZRT_URL="http://127.0.0.1:8080/v1"
RUN="$ROOT/runs/stack"
mkdir -p "$RUN"
# Every Herald model repo is public. A stale token in the environment makes public downloads fail with 401.
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN

say()  { printf '\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '    \033[33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\033[31mherald: %s\033[0m\n' "$*" >&2; exit 1; }
listening() { ss -ltn "sport = :$1" 2>/dev/null | grep -q LISTEN; }
pid_alive() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }
served() { curl -sf --max-time 5 "$ZRT_URL/models" 2>/dev/null | "$PY" -c "import json,sys; sys.exit(0 if sys.argv[1] in [m['id'] for m in json.load(sys.stdin)['data']] else 1)" "$1"; }
mem_avail_gb() { awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo; }

start_bg() {   # name, then the command; detached, logged, pid recorded
  local name="$1"; shift
  setsid nohup "$@" >"$RUN/$name.log" 2>&1 < /dev/null &
  echo $! >"$RUN/$name.pid"
}
stop_pid() {
  local name="$1"
  if pid_alive "$name"; then
    local pid; pid="$(cat "$RUN/$name.pid")"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
    ok "stopped $name (pid $pid)"
  fi
  rm -f "$RUN/$name.pid"
}

check_checkout() {
  say "Checkout"
  git fetch -q origin 2>/dev/null || warn "could not reach GitHub; using the local copy"
  if [ "${PULL:-0}" = 1 ]; then
    [ -z "$(git status --porcelain --untracked-files=no)" ] || die "uncommitted changes here; commit or discard them before --pull"
    if git symbolic-ref -q HEAD >/dev/null; then git merge -q --ff-only origin/main; else git checkout -q --detach origin/main; fi
  fi
  local head main; head="$(git rev-parse --short HEAD)"; main="$(git rev-parse --short origin/main 2>/dev/null || echo '?')"
  if [ "$head" = "$main" ]; then ok "on origin/main ($head)"
  elif git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then warn "$head is BEHIND origin/main ($main): run 'scripts/herald.sh up --pull'"
  else warn "$head is not origin/main ($main): running this checkout's code as it is"; fi
}

prepare_data() {
  say "One-time data"
  if [ -f data/terminology/rxnorm_index.json ]; then ok "RxNorm drug index"
  else
    warn "RxNorm drug index missing: building it once (about 10 minutes, downloads the public NLM release)"
    "$PY" scripts/build_rxnorm_index.py || die "RxNorm index build failed (see output above)"
    ok "RxNorm drug index built"
  fi
  "$PY" - <<'EOF' || die "could not fetch the Whisper / embedding weights"
from huggingface_hub import snapshot_download
for repo in ("openai/whisper-large-v3-turbo", "BAAI/bge-base-en-v1.5"):
    try:
        snapshot_download(repo, local_files_only=True)
    except Exception:
        print(f"    downloading {repo}"); snapshot_download(repo)
    print(f"    \033[32mok\033[0m  {repo} weights on disk")
EOF
}

ensure_model() {   # label, serve_models.sh target, GB it needs
  local label="$1" target="$2" need="$3"
  if served "$label"; then ok "$label serving"; return; fi
  [ -n "$target" ] || die "no serve_models.sh target known for label '$label': add it to serve_target_for()"
  local avail; avail="$(mem_avail_gb)"
  [ "$avail" -ge $((need + 16)) ] || die "$label is not served and only ${avail} GB is free (needs ~${need} GB + 16 GB headroom). Stop another model first: sg zrt -c 'zrt status'"
  warn "$label not served: starting it (${need} GB; first start can take several minutes)"
  scripts/serve_models.sh "$target" >"$RUN/serve-$label.log" 2>&1 || { tail -5 "$RUN/serve-$label.log"; die "zrt could not start $label (log: $RUN/serve-$label.log)"; }
  for _ in $(seq 180); do served "$label" && { ok "$label serving"; return; }; sleep 10; done
  die "$label did not become ready within 30 minutes: sg zrt -c 'zrt status'"
}

serve_target_for() {   # the scripts/serve_models.sh target that serves a given label
  case "$1" in
    ems-e-v2-fp8)   echo ems ;;
    qwen3vl-fp8)    echo vision ;;
    herald-f)       echo herald-f ;;
    herald-f4b-fp8) echo f4b ;;
    omni)           echo omni ;;
    *)              echo "" ;;
  esac
}

ensure_models() {
  say "Models (ZRT :8080)"
  sg zrt -c "zrt status" >/dev/null 2>&1 || die "ZRT is not reachable: is the zrt service running? (sg zrt -c 'zrt status')"
  # The target is derived from the LABEL, not hardcoded per job. Before this, the vision job always ran
  # `serve_models.sh vision`, which serves qwen3vl-fp8 -- so with HERALD_VISION_MODEL=herald-f (the shipping vision
  # model since 2026-09-25) an unserved box would quietly start the WRONG model and then fail the readiness check
  # against a label that was never asked for.
  ensure_model "$LLM" "$(serve_target_for "$LLM")" 18      # one at a time: never load two big models at once
  ensure_model "$VISION" "$(serve_target_for "$VISION")" 44
}

build_ui() {
  say "UI build"
  export PATH="$NODE_BIN:$PATH"
  command -v npm >/dev/null || die "node/npm not found at $NODE_BIN (conda env herald-ui)"
  if [ ! -d ui/node_modules ] || [ ui/package-lock.json -nt ui/node_modules/.package-lock.json ]; then
    (cd ui && npm ci --no-audit --no-fund >"$RUN/npm-ci.log" 2>&1) || die "npm ci failed (log: $RUN/npm-ci.log)"
  fi
  if [ ! -f ui/dist/index.html ] || [ -n "$(find ui/src ui/public ui/index.html ui/package.json -newer ui/dist/index.html -print -quit 2>/dev/null)" ]; then
    (cd ui && npm run build >"$RUN/ui-build.log" 2>&1) || die "UI build failed (log: $RUN/ui-build.log)"
    ok "UI built"
  else ok "UI up to date"; fi
}

ensure_link_and_ed() {
  say "ED screen and link"
  if listening "$ED_PORT"; then
    local owner; owner="$(ss -ltnpH "sport = :$ED_PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)"
    local where; where="$( [ -n "$owner" ] && readlink "/proc/$owner/cwd" || echo unknown)"
    if [ "$where" = "$ROOT" ]; then ok "ED screen already on :$ED_PORT"
    else warn "ED screen on :$ED_PORT is running from $where (not this checkout); left as is"; fi
  else
    start_bg ed "$PY" -m uvicorn ed_receiver.app:app --host 127.0.0.1 --port "$ED_PORT"
    for _ in $(seq 30); do listening "$ED_PORT" && break; sleep 0.5; done
    listening "$ED_PORT" && ok "ED screen on :$ED_PORT" || die "ED screen did not start (log: $RUN/ed.log)"
  fi
  if ! listening 8474; then
    start_bg toxiproxy "$TOXI/toxiproxy-server" -host 127.0.0.1 -port 8474
    for _ in $(seq 20); do listening 8474 && break; sleep 0.5; done
  fi
  listening 8474 || die "Toxiproxy did not start (log: $RUN/toxiproxy.log)"
  "$TOXI/toxiproxy-cli" inspect ed_link >/dev/null 2>&1 \
    || "$TOXI/toxiproxy-cli" create -l "127.0.0.1:$LINK_PORT" -u "127.0.0.1:$ED_PORT" ed_link >/dev/null
  ok "ED link emulator :$LINK_PORT -> :$ED_PORT (good / weak / down from the app)"
}

start_app() {
  say "Herald app"
  if pid_alive app; then stop_pid app; fi                       # always restart ours so it runs this checkout's code
  if listening "$PORT"; then die "port $PORT is used by a process this script did not start: HERALD_PORT=<free port> scripts/herald.sh up"; fi
  systemctl --user is-active --quiet herald-memguard.service 2>/dev/null && ok "memory guard active" || warn "memory guard not running (scripts/memguard.sh install)"
  HERALD_STT_PRELOAD=1 HERALD_LLM_MODEL="$LLM" HERALD_VISION_MODEL="$VISION" HERALD_ED_URL="http://127.0.0.1:$LINK_PORT" \
    start_bg app "$PY" -m uvicorn herald.app:app --host "${HERALD_BIND_HOST:-127.0.0.1}" --port "$PORT"
  local health=""
  for _ in $(seq 120); do
    pid_alive app || { tail -20 "$RUN/app.log"; die "the app exited during startup (log: $RUN/app.log)"; }
    health="$(curl -sf --max-time 5 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true)"
    [ -n "$health" ] && echo "$health" | "$PY" -c "import json,sys; h=json.load(sys.stdin); sys.exit(0 if h['stt_loaded'] and h['llm_available'] and h['vision_available'] else 1)" && break
    sleep 2
  done
  [ -n "$health" ] || die "the app never answered /api/health (log: $RUN/app.log)"
  echo "$health" | "$PY" -c "
import json,sys; h=json.load(sys.stdin)
row=lambda good,text: print(('    \033[32mok\033[0m  ' if good else '    \033[31mNO\033[0m  ')+text)
row(h['stt_loaded'], f\"speech-to-text {h['stt_model']} loaded\")
row(h['llm_available'], f\"extraction model {h['llm_model']}\")
row(h['vision_available'], f\"vision model {h['vision_model']}\")
row(bool(h.get('terminology')), 'RxNorm drug coding ' + (h['terminology'] or {}).get('rxnorm_release', 'OFF'))
row(h.get('cloud_ai_calls', 0) == 0, f\"cloud AI calls: {h.get('cloud_ai_calls', 0)}\")
sys.exit(0 if h['stt_loaded'] and h['llm_available'] and h['vision_available'] else 1)" || die "not everything is ready (log: $RUN/app.log)"
  # County protocol index: built on first start (embeds ~1,800 sections on the CPU, a couple of minutes), cached after.
  local ready=""
  for _ in $(seq 90); do
    ready="$(curl -sf --max-time 5 "http://127.0.0.1:$PORT/api/protocols" | "$PY" -c "import json,sys; s=json.load(sys.stdin); print(s.get('sections', 0) if s.get('ready') else '')" 2>/dev/null || true)"
    [ -n "$ready" ] && break
    sleep 5
  done
  [ -n "$ready" ] && ok "county protocols indexed ($ready sections)" || warn "county protocol index still building; protocol passages appear when it finishes"
}

print_urls() {
  local ip; ip="$(hostname -I | awk '{print $1}')"
  cat <<EOF

Herald is up.  From your laptop:
    ssh -L $PORT:localhost:$PORT -L $ED_PORT:localhost:$ED_PORT $(whoami)@$ip
then open
    medic screen      http://localhost:$PORT
    ED screen         http://localhost:$ED_PORT
    monitor to film   http://localhost:$PORT/monitor.html
    recorded call     http://localhost:$PORT/?fixture=stroke_demo
(the SSH tunnel makes the page "localhost", which the browser requires for the microphone and camera)
Logs: scripts/herald.sh logs      Stop: scripts/herald.sh down
EOF
}

status() {
  say "Checkout"; echo "    $(git rev-parse --short HEAD) $(git log -1 --format=%s | cut -c1-80)"
  say "Models"; sg zrt -c "zrt status" 2>/dev/null | grep -E "│ [0-9]" | awk -F'│' '{printf "    %-14s %-7s %s\n", $4, $6, $7}' || warn "ZRT not reachable"
  say "Services"
  for p in "$ED_PORT:ED screen" "8474:link emulator" "$PORT:Herald app"; do
    listening "${p%%:*}" && ok "${p#*:} on :${p%%:*}" || warn "${p#*:} not running on :${p%%:*}"
  done
  curl -sf --max-time 5 "http://127.0.0.1:$PORT/api/health" | "$PY" -c "import json,sys; h=json.load(sys.stdin); print(f\"    speech={h['stt_loaded']} extraction={h['llm_available']} ({h['llm_model']}) vision={h['vision_available']} ({h['vision_model']})\")" 2>/dev/null || true
}

case "${1:-}" in
  up)
    [ "${2:-}" = "--pull" ] && PULL=1
    check_checkout; prepare_data; ensure_models; build_ui; ensure_link_and_ed; start_app; print_urls ;;
  down)
    say "Stopping (models keep serving; stop them with: sg zrt -c 'zrt stop <pid>')"
    stop_pid app; stop_pid ed; stop_pid toxiproxy ;;
  status) status ;;
  logs) touch "$RUN/app.log" "$RUN/ed.log"; tail -n 40 -F "$RUN"/app.log "$RUN"/ed.log ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
