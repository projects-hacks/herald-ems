# Relay benchmark (E2)

`eval/bench_relay.py` evaluates the real relay HTTP route through Toxiproxy into the mock ED receiver. It uses a fixed, confirmed stroke record so the result measures packet ordering, link transport, acknowledgement, and reconciliation—not model extraction.

Run it with an isolated ED receiver and proxy:

```bash
PY=~/miniforge3/envs/zgx/bin/python
$PY -m uvicorn ed_receiver.app:app --host 127.0.0.1 --port 8210
~/.local/bin/toxiproxy-server -host 127.0.0.1 -port 8475
$PY eval/bench_relay.py --toxiproxy-url http://127.0.0.1:8475 \
  --ed-url http://127.0.0.1:8210 --listen 127.0.0.1:9101 --runs 3
```

The benchmark configures 1 KB/s in both directions and 800 ms downstream latency for the first critical packet, then restores the same real proxy to a good link and waits for the full-record synchronization. One JSONL result per run is appended to `eval/results.jsonl`; the final printed object gives the min/mean/max spread for deck use.

## Measured 2026-09-25

Three real HTTP runs, using the prescribed 1 KB/s + 800 ms configuration:

| Metric | Result (min–max; mean) |
|---|---|
| First critical acknowledgement | 1,424–1,435 ms; 1,428 ms |
| Critical packet | 409 B |
| Full-record sync | 3,120 B |
| Critical packet relative to full sync | 13.11% |
| Reconciled after recovery | 1,434–1,446 ms; 1,439 ms |
| Duplicates / lost critical values | 0 / 0 in all three runs |

These are genuine relay/receiver measurements, not a model measurement. The prescribed link configuration has throttling and latency but no injected connection resets, so the duplicate count confirms receiver idempotency on this path but does not by itself measure retry behavior. Retry/loss behavior remains covered by the seeded relay tests.
