# Herald pre-demo runbook

Run this checklist on the ZGX Nano before rehearsal, recording, or judging. Port `8100` is the shared demo;
contributors use `8101`–`8104`. Never restart a shared model without Rajeev coordinating it.

## 1. Repository and processes

```bash
cd ~/Documents/team-last-minute/herald-ems
git status --short --branch
~/miniforge3/envs/zgx/bin/python -m pytest -q
sg zrt -c "zrt status"
free -g
scripts/memguard.sh status
systemctl show -p RuntimeWatchdogUSec
```

`scripts/memguard.sh status` must report an active service and a fresh heartbeat. Record `RuntimeWatchdogUSec`
with the preflight evidence; do not change the host watchdog setting during demo preparation. If the memory guard
check fails, stop and give Rajeev the output instead of starting the demo.

> **The memory-safety layer ships with the run F commit.** `scripts/memguard.sh`, `scripts/memguard.py`,
> `scripts/memguard/`, `scripts/run_job.py`, `scripts/demo_mode.sh` and `scripts/run_demo.sh` are named throughout
> this runbook and in `AGENTS.md`, and they were untracked until that commit. A clone made before it cannot run
> steps 1, 3 or 5. Check them in first (`git log --oneline -1 -- scripts/run_job.py`) rather than substituting
> `run_dev.sh` on the demo port. See `docs/MEMORY_SAFETY.md`.

The watchdog line matters for a second reason: the box hard-hung four times on 2026-09-24/25 (19:36, 23:10, 01:42,
05:13 UTC) with no kernel record — no OOM, no panic, no GPU Xid, and an empty `/sys/fs/pstore` despite a registered
`efi_pstore` backend. Each time the SBSA watchdog reset it after 60 s and systemd brought everything back. If the
machine reboots mid-rehearsal, that is the known fault: re-run this checklist from step 1 rather than debugging it.

The final model label is defined by `scripts/serve_models.sh`:

- `herald-f` — speech-to-facts extraction, photos, protocol figures, and passage reranking.

It must be `Ready`. Do not start a duplicate service. If it is absent, give Rajeev the output of
`zrt status`; model starts take minutes and require shared-memory planning.

### Kernel-backend check

```bash
grep -i "backend" /opt/hp/zrt/run/vllm-herald-f.log | tail -1
```

Record the backend line exactly as the final service reports it. The old S7 wording asked for MARLIN on `omni`;
that retired label is not a valid acceptance check for the final stack.

## 2. ED receiver and link

Start these only if they are not already listening:

```bash
ss -ltn | grep -E ':(8200|9000) '
~/miniforge3/envs/zgx/bin/python -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200
scripts/link.sh start 127.0.0.1:8200
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:8200/ping
curl -fsS http://127.0.0.1:9000/ping
```

Both must answer successfully. For the real two-screen demonstration, replace the local ED upstream with the
teammate laptop address and verify the second URL through Toxiproxy.

## 3. Start Herald

```bash
scripts/demo_mode.sh on
HERALD_ED_URL=http://127.0.0.1:9000 \
HERALD_LLM_MODEL=herald-f \
HERALD_VISION_MODEL=herald-f \
scripts/run_demo.sh
```

Do not substitute `run_dev.sh` on the demo port: `run_demo.sh` disables reload, preloads Whisper, and refuses to
start unless the memory guard is healthy and demo mode is on.

If the run F gates sent us to the two-model configuration, use §7.3 instead of this command and expect two `Ready`
labels in step 1 rather than one.

Wait for the server, then check:

```bash
curl -fsS http://127.0.0.1:8100/api/health | python3 -m json.tool
curl -fsS -X POST http://127.0.0.1:8100/api/netem/good | python3 -m json.tool
```

The health response must show both expected model labels, `llm_available: true`, `vision_available: true`,
`stt_loaded: true`, Santa Clara County, and zero cloud AI calls.

## 4. Warm and rehearse

Warm the extractor by replaying the real scenario once; it makes more than three extraction requests:

```bash
~/miniforge3/envs/zgx/bin/python scripts/replay.py scenarios/stroke_demo.json \
  --url http://127.0.0.1:8100 --fast
```

Warm the vision model three times with synthetic, non-patient data:

```bash
for n in 1 2 3; do
  curl -fsS -X POST http://127.0.0.1:8100/api/photo \
    -F file=@eval/photos/synthetic_pill_warfarin.jpg -F mode=pill_bottle >/dev/null
done
```

Then rehearse the network sequence: Shift+W (weak), Shift+D (offline), Shift+G (restore). Confirm that the NOW
screen queues updates while offline, the ED screen receives the critical packet after restore, and both screens
remain responsive.

Reset to a clean stroke incident:

```bash
curl -fsS -X POST http://127.0.0.1:8100/api/incident \
  -H 'content-type: application/json' -d '{"dispatch":"possible stroke"}' >/dev/null
curl -fsS -X POST http://127.0.0.1:8100/api/netem/good >/dev/null
```

## 5. Stability soak

Use a contributor port for the soak, never the live demo port:

```bash
HERALD_ED_URL=http://127.0.0.1:9000 \
HERALD_LLM_MODEL=herald-f \
HERALD_VISION_MODEL=herald-f \
PORT=8103 scripts/run_dev.sh
```

In another terminal:

```bash
~/miniforge3/envs/zgx/bin/python scripts/soak.py \
  --url http://127.0.0.1:8103 --duration-minutes 30 --require-pass
```

The harness resets and replays the stroke incident repeatedly, authorizes the relay, samples `/proc/meminfo` and
`zrt status` every 30 seconds, and writes ignored evidence files under `runs/`:

- `runs/soak_<timestamp>.jsonl` — every sample, model phase, and iteration;
- `runs/soak_<timestamp>.summary.json` — acceptance summary.

The acceptance bar is zero model errors, zero relay failures, last-five-minute model p95 no more than 20% above
the first five minutes, final memory growth no more than 1 GiB, and no concurrent training, model download, or
benchmark process. The harness records competing jobs because this is a shared machine. If a check fails, keep the
evidence and find the root cause before calling it a model failure.

By default the harness aborts after detecting contention, so it does not waste a 30-minute slot. Use
`--allow-contention` only to diagnose shared-load behavior; such a run cannot pass.

### 2026-09-24 initial evidence

The first full run completed 30.1 minutes, 157 scenario loops and 1,413 model phases with zero model errors,
zero scenario errors, zero relay failures, final memory 86 MiB below baseline, and peak growth 528 MiB. It did
not pass: model p95 rose from 2.63 s in the first five minutes to 4.78 s in the last five minutes (+81.8%). A
Qwen model download and a `vision_bench.py` run overlapped the final window on the shared Nano. Two attempted
isolated follow-ups were also caught overlapping subsequent vision benchmarks. Those runs are evidence that the
error and memory paths are stable under contention, but they are not valid latency-soak results. Repeat the full
run in a team-coordinated exclusive GPU window before marking C3.8 complete.

After adding automatic contention aborts, a final attempt ran uncontended for 5.2 minutes: 29 scenarios,
261 model phases, zero errors, zero relay failures, and p95 2.625 s. It then correctly aborted when a
`vision_bench.py` rerank/flowchart job started. This confirms the baseline returns when the shared GPU is idle and
that the guard prevents another invalid 30-minute run; it does not replace the pending full acceptance run.

## 6. Final stage check

1. Verify both displays from three metres away.
2. Confirm microphone access through a localhost port forward or HTTPS.
3. Confirm the ED receiver is on the intended second machine/network.
4. Run one full scenario, including provenance playback and the contradiction confirmation.
5. Run weak → down → good once more.
6. Reset the ED receiver and Herald incident.
7. Leave the link `good`, `herald-f` `Ready`, and the browser on the clean opening state.
8. After judging is complete, run `scripts/demo_mode.sh off`; never turn it off while the protected demo is active.

## 7. Split stack (two models, one job each) — `docs/TRAINING_PLAN.md` §7a

**Skip this section for the normal demo.** The stack above is one model, `herald-f`, doing every job. This section is
the contingency, and it is the *third* choice, not the first.

**When to use it.** Only if **both** run F epoch adapters win speech and photos but fail the kept-ability gates —
protocol reranking on the 59 questions, 700-A13 figure transcription, the 10-line EN↔ES translation check
(`TRAINING_PLAN` §6a). If only one epoch fails them, ship the other one: that is cheaper and keeps a single model. If
speech or photos also fail, take the §7 rollback in `TRAINING_PLAN` instead.

**What it does.** The fine-tune keeps the jobs it is good at; the untuned base keeps the jobs it lost.

| job | model | setting |
|---|---|---|
| speech → facts | `herald-f` | `HERALD_LLM_MODEL=herald-f` |
| photo reading | `herald-f` | `HERALD_VISION_MODEL=herald-f` |
| protocol reranking, figure transcription, translation | `qwen3vl-fp8` | `HERALD_KNOWLEDGE_MODEL=qwen3vl-fp8` |

Leave `HERALD_KNOWLEDGE_MODEL` unset for the single-model stack; the knowledge client is then the *same object* as the
photo client and nothing changes. Both labels answer on one endpoint — ZRT's proxy routes by label on
`127.0.0.1:8080` (`/opt/hp/zrt/proxy.json` is one host and port with a `services` list) — so there is no second URL to
configure.

### 7.1 Check it fits, before starting anything

Two resident 30B models is the entire cost of this decision. Measure with **the app and Whisper already up**, because
that is the state it has to survive:

```bash
scripts/memguard.sh status
grep MemAvailable /proc/meminfo
```

The arithmetic to check that against: at `--gpu-memory-fraction 0.30` each model is given ~36 GiB of the 121.6 GiB.
About 31 GiB of that is FP8 weights, leaving only **~5 GiB for the KV cache**, and vLLM refuses to start if the cache
cannot hold a single `--max-model-len` sequence. So:

- **`--max-model-len` must come down from 16384.** 8192 is what `scripts/serve_models.sh` uses, which clears the
  largest real job (figure transcription, ~2.7k tokens) with room to spare. Lower it further if a model refuses to
  start.
- The two together (~72 GiB) still have to coexist with the app, Whisper and the page cache.
- ZRT counts **free** memory, not reclaimable page cache, so it can refuse while `MemAvailable` looks healthy. Drop the
  page cache of large files you own first (`AGENTS.md` pitfalls).

If it does not fit, stop: ship epoch 1 (§6a rule 2) or take the rollback. Do not shrink the demo to make room.

### 7.2 Start the two models, one at a time

The block is in `scripts/serve_models.sh`, **commented out** on purpose. Uncomment it, then:

```bash
scripts/serve_models.sh split
```

`zrt serve` runs in the **foreground** and dies with the shell that started it, so by hand, launch each detached and
wait for `Ready` before the second:

```bash
setsid nohup env MAX_JOBS=3 NVCC_THREADS=1 sg zrt -c "zrt serve ..." > runs/serve/<label>.log 2>&1 < /dev/null &
sg zrt -c "zrt status"        # wait for Ready before starting the next one
```

### 7.3 Point the app at them

Step 3 above, with one variable added:

```bash
scripts/demo_mode.sh on
HERALD_ED_URL=http://127.0.0.1:9000 \
HERALD_LLM_MODEL=herald-f \
HERALD_VISION_MODEL=herald-f \
HERALD_KNOWLEDGE_MODEL=qwen3vl-fp8 \
scripts/run_demo.sh
```

### 7.4 Verify the split is live, and say it honestly

```bash
curl -fsS http://127.0.0.1:8100/api/stack | python3 -c "import json,sys; print(json.load(sys.stdin)['jobs'])"
```

expects

```
{'extraction': 'herald-f', 'photos': 'herald-f', 'knowledge': 'qwen3vl-fp8'}
```

`/api/telemetry` reports the same `jobs` block. Both appear **only** when the split is configured, so nothing on screen
implies one model is doing everything when two are (`docs/UX_PLAN.md` §5.9c). On stage, say "two models, one job each".
Re-run the kept-ability gates against the split before quoting those numbers, and note that step 1's model check above
expects one `Ready` label — in this configuration there are two.

### 7.5 Going back

Unset `HERALD_KNOWLEDGE_MODEL`, restart the app, and stop whichever model is no longer needed. No reindexing and no
retraining: the knowledge base, prompts and county configuration are untouched by this switch.

> **Untested.** Written while the box was training; the two-model configuration has never been started. Rehearse it
> once off the demo clock before relying on it.
