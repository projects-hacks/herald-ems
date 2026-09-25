# Runtime and soak checks

Use synthetic incidents on a contributor port (`8101`–`8104`). Port `8100` and the shared model services belong to the active deployment; coordinate with its owner before starting workloads. Do not load models during training or bypass that deployment's memory guard. If its guarded launcher is absent from this checkout, use the owner-approved deployment checkout.

## Before starting

- Run `python -m pytest -q` and the UI checks in the README. These tests use fake model adapters.
- Build the medic app with `(cd ui && npm ci && npm run build)`.
- Inspect `sg zrt -c "zrt status"`, memory availability and the deployment's guard status. Confirm the actual extraction and vision labels with the owner; historical benchmark labels are not serving readiness.
- Use the approved launcher and labels. Do not start a duplicate model or replace the shared service. Check `/api/health` for the expected labels and model availability before real inference.

## ED and capture

If the receiver and link proxy are not already running, use separate terminals:

```bash
python -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200
scripts/link.sh start 127.0.0.1:8200
```

Verify both `http://127.0.0.1:8200/ping` and `http://127.0.0.1:9000/ping`. Point the approved Herald instance at `HERALD_ED_URL=http://127.0.0.1:9000`. For a second-machine test, use that receiver's address as the link proxy upstream.

Run `python scripts/replay.py scenarios/stroke_demo.json --url http://127.0.0.1:8103 --fast` only on the approved disposable instance; replay creates an incident and invokes extraction. In Settings, switch the link weak → down → good. Check queued updates, critical delivery, full-history reconciliation and explicit clinician receipt. Test microphone access over localhost/HTTPS and the physical camera path in `AGENTIC_CAPTURE.md`.

## Stability soak

With the approved instance already running on the isolated port:

```bash
python scripts/soak.py --url http://127.0.0.1:8103 --duration-minutes 30 --require-pass
```

The harness repeatedly resets a synthetic incident, samples memory/model readiness and writes ignored evidence under `runs/`. Acceptance requires zero model/relay errors, last-five-minute model p95 within 20% of the first five minutes, final memory growth at most 1 GiB, and no concurrent training, downloads or benchmarks. The default contention abort prevents an invalid run. `--allow-contention` is diagnostic only and cannot produce a passing acceptance result.

Keep the samples and summary for failures and investigate the cause. Layout checks and short no-model runs do not replace the hardware soak.

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
