#!/usr/bin/env bash
# Rebuild Herald from a clean clone (docs/TASK_SPECS.md S2). The Nano is wiped after the event, so this is
# how anyone (teammate, judge, or a future box) gets from `git clone` to a running server.
#
#   scripts/setup.sh                 # everything below
#   scripts/setup.sh --skip-ui       # skip the UI build (needs node >= 22)
#   scripts/setup.sh --skip-rxnorm   # skip the RxNorm index (~10 min first time, needs internet)
#
# Idempotent: safe to re-run. Every step prints what it did, and what to do if it failed.
# Does NOT start any model server: zrt serve takes 3-23 minutes and shares one GPU across the whole team,
# so starting it is a decision, not a side effect of setup. See step 4 for the exact commands to run yourself.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SKIP_UI=0; SKIP_RXNORM=0
for arg in "$@"; do
  case "$arg" in
    --skip-ui) SKIP_UI=1 ;;
    --skip-rxnorm) SKIP_RXNORM=1 ;;
    *) echo "unknown flag: $arg"; exit 1 ;;
  esac
done

ok()   { echo "  OK   $*"; }
warn() { echo "  !!   $*"; }
step() { echo; echo "== $* =="; }

FAIL=0

# ---------------------------------------------------------------------------
step "1. Platform"
# ---------------------------------------------------------------------------
ARCH="$(uname -m)"
if [ "$ARCH" = "aarch64" ]; then
  ok "arch: aarch64"
else
  warn "arch is $ARCH, not aarch64. Herald targets the ZGX Nano (GB10, aarch64). Continuing, but model serving" \
       "(ZRT/vLLM) and the pinned torch wheel are built for aarch64 and will likely fail here."
fi

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  ok "nvidia-smi: $(nvidia-smi -L | head -1)"
else
  warn "nvidia-smi not found or no GPU visible. Local inference needs a CUDA GPU; the ZGX Nano exposes the GB10" \
       "as sm_121. Without a GPU, run_dev.sh will still start (Whisper/vLLM calls will fail)."
fi

PY="${HERALD_PY:-$HOME/miniforge3/envs/zgx/bin/python}"
if [ -x "$PY" ]; then
  TORCH_INFO="$("$PY" -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())' 2>&1)"
  if [ $? -eq 0 ]; then
    ok "zgx env: $PY  (torch $TORCH_INFO)"
  else
    warn "zgx env found at $PY but torch import failed: $TORCH_INFO"
    FAIL=1
  fi
else
  warn "no zgx conda env at $PY. This is the shared env with torch 2.14.0+cu130 built for GB10 (sm_121); pip" \
       "cannot rebuild it (no matching wheel on PyPI). Ask a teammate for read access to the existing env, or" \
       "follow AGENTS.md / the team context doc to rebuild it from the NVIDIA/PyTorch aarch64+CUDA13 wheels." \
       "Set HERALD_PY=/path/to/python if your env lives somewhere else."
  FAIL=1
fi

# ---------------------------------------------------------------------------
step "2. Python dependencies"
# ---------------------------------------------------------------------------
if [ -x "$PY" ]; then
  CONSTRAINTS=/tmp/herald-zgx-constraints.txt
  "$PY" -m pip freeze 2>/dev/null | grep -iE '^(torch|torchaudio|torchvision|transformers|numpy)==' > "$CONSTRAINTS"
  if [ -s "$CONSTRAINTS" ]; then
    ok "pinned constraints written to $CONSTRAINTS (protects torch/torchaudio/torchvision/transformers/numpy)"
  else
    warn "could not read existing torch/transformers versions to pin; installing without constraints" \
         "(risk: pip may upgrade torch and break the GB10-tuned wheel)"
  fi
  if "$PY" -m pip install -q -c "$CONSTRAINTS" -r requirements.txt; then
    ok "requirements.txt installed"
  else
    warn "pip install failed. See the error above. Common cause on this box: a requirement wants a version" \
         "of torch/transformers newer than the pinned one -- resolve by hand, don't drop the constraints file."
    FAIL=1
  fi
  if "$PY" -m pip check >/tmp/herald-pip-check.log 2>&1; then
    ok "pip check: no broken requirements"
  else
    warn "pip check found issues (see /tmp/herald-pip-check.log). Often harmless (e.g. an unrelated tool's" \
         "extra), but re-check if anything under herald/, eval/, or scripts/ fails to import."
  fi
else
  warn "skipped (no zgx env; see step 1)"
  FAIL=1
fi

# ---------------------------------------------------------------------------
step "3. Local models (not started automatically)"
# ---------------------------------------------------------------------------
if command -v zrt >/dev/null 2>&1; then
  ok "zrt found: $(zrt version 2>&1 | head -1)"
  if id -nG "$USER" 2>/dev/null | tr ' ' '\n' | grep -qx zrt; then
    ok "user $USER is in the zrt group"
  else
    warn "user $USER is not in the zrt group. Ask whoever has sudo to run: sudo usermod -aG zrt $USER" \
         "(then open a new shell). Until then, use: sg zrt -c \"zrt ...\""
  fi
  STATUS_JSON="$(zrt status --json 2>/dev/null || true)"
  for label in ems-e-v2-fp8 qwen3vl-fp8; do
    if echo "$STATUS_JSON" | "$PY" -c "
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
procs = [p for p in d.get('processes', []) if p.get('label') == sys.argv[1]]
sys.exit(0 if any(p.get('state') == 'Ready' for p in procs) else 1)
" "$label" 2>/dev/null; then
      ok "$label is serving (zrt status)"
    else
      warn "$label is not serving. Start it with (takes 3-23 min the first time; shares the one GPU," \
           "coordinate with the team before running):"
      echo "        scripts/serve_models.sh $([ "$label" = ems-e-v2-fp8 ] && echo ems || echo vision)"
      echo "     (public repos; no token needed)"
    fi
  done
else
  warn "zrt not found on PATH. Install/setup per AGENTS.md (sudo zrt setup --mode system), or serve the same" \
       "models with plain vLLM/Ollama/llama.cpp and point HERALD_LLM_URL at them (herald/config/settings.py)."
fi

# ---------------------------------------------------------------------------
step "4. UI build"
# ---------------------------------------------------------------------------
if [ "$SKIP_UI" = 1 ]; then
  warn "skipped (--skip-ui). / will fall back to the classic web/ screens unless ui/dist/index.html exists" \
       "from a previous build."
elif [ -d ui ]; then
  NODE_BIN=""
  for cand in "$(command -v node 2>/dev/null)" "$HOME/miniforge3/envs/herald-ui/bin/node"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then NODE_BIN="$cand"; break; fi
  done
  if [ -n "$NODE_BIN" ]; then
    NODE_DIR="$(dirname "$NODE_BIN")"
    NODE_VER="$("$NODE_BIN" -v)"
    ok "node found: $NODE_VER ($NODE_BIN)"
    (
      export PATH="$NODE_DIR:$PATH"
      cd ui
      if npm ci --silent 2>/tmp/herald-npm-install.log || npm install --silent 2>>/tmp/herald-npm-install.log; then
        echo "  OK   npm dependencies installed"
      else
        echo "  !!   npm install failed (see /tmp/herald-npm-install.log)"
        exit 1
      fi
      if npm run build --silent; then
        echo "  OK   ui/dist built (served at / when HERALD_UI=new, the default)"
      else
        echo "  !!   npm run build failed"
        exit 1
      fi
    ) || FAIL=1
  else
    warn "no node >= 22 on PATH and none at ~/miniforge3/envs/herald-ui/bin/node. Install one:" \
         "conda create -n herald-ui -c conda-forge 'nodejs>=22' -y   (or apt/nvm equivalent on a non-Nano box)." \
         "Falling back to the classic web/ screens at / until the UI is built."
  fi
else
  warn "no ui/ directory; nothing to build"
fi

# ---------------------------------------------------------------------------
step "5. RxNorm drug-name index"
# ---------------------------------------------------------------------------
if [ "$SKIP_RXNORM" = 1 ]; then
  warn "skipped (--skip-rxnorm). Drug-name coding (herald/terminology/) will report names as unresolved" \
       "until data/terminology/rxnorm_index.json exists."
elif [ -x "$PY" ]; then
  if [ -f data/terminology/rxnorm_index.json ]; then
    ok "RxNorm index already built (data/terminology/rxnorm_index.json)"
  else
    echo "  building RxNorm index (first time: ~10 min, needs internet for the NLM release + RxNav brands)..."
    if "$PY" scripts/build_rxnorm_index.py; then
      ok "RxNorm index built"
    else
      warn "RxNorm index build failed. Drug-name coding will be unavailable but the rest of Herald still runs" \
           "(config/settings.py HERALD_TERMINOLOGY=0 to silence the warning). Re-run" \
           "scripts/build_rxnorm_index.py by hand to see the error."
    fi
  fi
else
  warn "skipped (no zgx env; see step 1)"
fi

# ---------------------------------------------------------------------------
step "6. Tests"
# ---------------------------------------------------------------------------
if [ -x "$PY" ]; then
  if "$PY" -m pytest -q 2>&1 | tee /tmp/herald-pytest.log | tail -5; then
    ok "tests pass (full log: /tmp/herald-pytest.log)"
  else
    warn "tests failed (see /tmp/herald-pytest.log). Don't ignore this: AGENTS.md rule 8 requires tests to pass."
    FAIL=1
  fi
else
  warn "skipped (no zgx env; see step 1)"
fi

# ---------------------------------------------------------------------------
step "Run commands"
# ---------------------------------------------------------------------------
cat <<'EOF'
  Server (pick your own port; 8100 is the shared demo instance):
    PORT=8101 scripts/run_dev.sh

  ED receiver (a second machine or a second terminal on this one):
    ~/miniforge3/envs/zgx/bin/python -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200

  Emulated weak link (Toxiproxy, no root):
    scripts/link.sh start 127.0.0.1:8200
    HERALD_ED_URL=http://127.0.0.1:9000 PORT=8101 scripts/run_dev.sh

  Replay the stroke demo (no models needed with --no-llm):
    ~/miniforge3/envs/zgx/bin/python scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8101 --no-llm

  Health check once the server is up:
    curl -s http://localhost:8101/api/health
EOF

echo
if [ "$FAIL" = 1 ]; then
  echo "== setup finished with warnings/failures above. Fix those before relying on this clone. =="
  exit 1
else
  echo "== setup complete =="
  exit 0
fi
