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
