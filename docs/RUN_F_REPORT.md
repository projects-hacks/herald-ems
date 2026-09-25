# Run F training report

**Status: training complete and clean. The model does not ship.** 488/488 optimizer steps, supervisor exit code 0,
`DONE` written, both epoch adapters verified. The gate table then ran, and `herald-f` failed the protocol-reranking
gate, which §6a treats as blocking. **The shipping stack is the TRAINING_PLAN §7 rollback: Whisper +
`ems-e-v2-fp8` for extraction + untuned `qwen3vl-fp8` for photos and protocol knowledge** (owner, 2026-09-25).

Run F is not a wasted run: it produced the best extraction model we have measured (held-out f1 0.964 vs E v2's
0.949) and it is the only model that reads the sepsis flag at all (recall 0.889 vs 0.111). It loses on the abilities
we are not allowed to regress, and on the stroke screen. Both adapters stay public as research artifacts with these
numbers on the model card. §8 is the gate table, §9 the decision, §10 the limitations that apply to the shipped
product regardless of which model serves it.

| | |
|---|---|
| Finished | 2026-09-25 **09:22:03 UTC** (02:22 PDT) |
| Base | `Qwen/Qwen3-VL-30B-A3B-Instruct` |
| Steps | 488 / 488 (2 epochs, ends at 244 and 488) |
| `DONE` | `{"step": 488, "t": 1790328123.4}` |
| Wall clock | 04:16:45 → 09:22:03 UTC = **5 h 05 m**, including 2 reboots and 3 deliberate restarts |
| Peak GPU memory | **78.5 GiB** of 121.6 |
| Throughput | 336.4 padded tokens/s (final segment: 1,898,633 tokens in 5,643 s) |
| NaN encountered | no |

---

## 1. Dev loss, and why epoch 2 was the checkpoint to gate

*(Epoch 2 won the checkpoint choice. It then lost the ship decision at the gates — §8, §9.)*

| step | text | image | replay | |
|---:|---:|---:|---:|---|
| 50 | 0.1883 | 0.2822 | 0.0894 | baseline |
| 100 | 0.1287 | 0.2510 | 0.0920 | |
| 122 | 0.1195 | 0.2681 | 0.0961 | |
| **244** | **0.0899** | **0.2292** | **0.1393** | **epoch 1** |
| 366 | 0.0835 | 0.2105 | 0.1348 | |
| **488** | **0.0819** | **0.2042** | **0.1322** | **epoch 2** |

**Epoch 2 is better on all three splits: text −8.9%, image −10.9%, replay −5.1%.** No tradeoff, no axis on which epoch 1 wins.

That result changed the plan. TRAINING_PLAN §6a rule 2 originally said epoch 1 ships if epoch 2 fails kept abilities — written before either was measured, on the assumption the later adapter might trade retained ability for task accuracy. It didn't. So (§6b):

- Epoch 2 is merged, served and gated **first**; epoch 1 is not served and not gated.
- If epoch 2 passes kept abilities, **epoch 1 is never tested** — it cannot win.
- If epoch 2 fails, go to the **4B run F + untuned `qwen3vl-fp8`** fallback or the split stack, **not to epoch 1**: epoch 1 retained those abilities *worse* (replay 0.1393 vs 0.1322), so it is the less likely to pass the same gate.
- Both epoch-1 artifacts stay on disk and on the private repo. Keeping them is free; testing them costs an hour and a model swap.

### Two honest limits on the replay number

**The replay dev set is 40 rows.** That is small enough that a single pass moves the number visibly, and it is why the +0.0172 image blip at step 122 reversed completely by 366.

**The step-50 baseline is close to base weights** — 50 of 488 steps, LoRA barely trained. So "epoch 2 is +48% above baseline" measures how far the adapter moved from an almost-untuned starting point, on a small sample. **It is a direction signal, not a magnitude claim.** It says drift happened and which way it is heading; it does not say how much ability was lost.

**The kept-ability gates decide that** — protocol reranking on 59 questions, 700-A13 figure transcription, the 10-line EN↔ES translation check — measured on the real tasks. They are blocking per §6a: an epoch failing them cannot ship whatever its speech numbers are.

---

## 2. What was trained

**LoRA** — rank 16, alpha 32, dropout 0 (required by PEFT's `target_parameters`), language model only:

- attention and MLP projections `q,k,v,o,gate,up,down_proj` under `language_model`
- **every expert**: `mlp.experts.gate_up_proj`, `mlp.experts.down_proj`; the router stays frozen
- **642,514,944** trainable parameters (attention 13,369,344 + experts 629,145,600)
- the vision tower is untouched, so the served tower is identical to the benchmarked one

**Data** — one plan of 17,112 rows in fixed order, 976 micro-batches, **5,428,833 padded tokens** (5,289,700 real), **0 rows dropped** for length:

| kind | rows used | available |
|---|---|---|
| text (speech → facts) | 13,880 | 6,940 |
| image (photos, forms) | 2,400 | 3,460 |
| replay (rerank, figures, translation) | 832 | 416 |

Held out: 150 text, 60 image, 40 replay.

---

## 3. Artifacts and run integrity

Adapters saved and independently backed up, verified by **sha256, not file size**:

| adapter | bytes | sha256 | whole-dir digest | backup |
|---|---|---|---|---|
| `epoch-1` (step 244) | 2,570,148,264 | `fc23712e38a21288` | `b4b9bb6c9fe0d6b2` | identical |
| `epoch-2` (step 488) | 2,570,148,264 | `7b2e3a9fbd10e6bd` | `53e283904ed39a7b` | identical |

**Plan fingerprint `28ca4d23d92b3f651c7b275e` held across every resume.** The run was interrupted five times and never trained the wrong rows:

| resumed from step | at UTC | cause |
|---:|---|---|
| 0 | 04:16:45 | initial start |
| 30 | 04:35:28 | deliberate: memory fix (`--reclaim-gib 0`) |
| 80 | 05:07:00 | deliberate: cadence change |
| 90 | 05:18:25 | **freeze** (05:13) |
| 100 | 05:30:21 | deliberate: cadence bug fix |
| 320 | 07:47:04 | **freeze** (07:32) |

Each freeze cost only work since the last complete checkpoint: **1 step** and **~7 steps**.

---

## 4. Problems found during the run

**a. The cadence change was silently ignored on resume.** `checkpoint_steps` 10→20 and `eval_steps` 50→122 went into `training_args.bin` and had no effect: transformers' `DefaultFlowCallback` reads `TrainerState`, and `Trainer._init_training_state` replaces the whole state with the checkpoint's on resume. The tell was a save at step 90, impossible under `save_steps=20` — the same checkpoint reported `save_steps: 20` in args and `10` in state. Fixed with a `CadenceFromArgs` callback in `on_train_begin`, which runs after the restore. Verified live; checkpoints then went 100 → 120 with no 110.

**b. `eval_steps: 50` measured neither epoch end.** 488 is not a multiple of 50, so **there would have been no dev pass at step 488 at all** and epoch 2 would have been judged on step-450 numbers — the very comparison this decision rests on. A correctness fix, not a speed-up.

**c. `herald_epoch.json` carries the previous pass's losses — still open.** The adapter is saved in `on_step_end`, which fires before that step's dev pass reaches `log_history`. `epoch-1` says step 244 but holds step 122's eval; `epoch-2` says 488 but holds 366's. **Decide from `log.jsonl`.** Fix deferred.

**d. `reference_tokens_per_s` was wrong by 2×** (180 assumed, 373 measured), so the checkpoint cadence had been sized against the wrong number.

---

## 5. Platform: five hard events, and the cause

**Not one cause.** The attribution matters:

| time (UTC) | cause |
|---|---|
| Thu 19:35 | **real OOM** — parallel model loads beside three vLLM services |
| 23:10 | power-spike signature |
| 01:42 | power-spike signature |
| 05:13 | **ambiguous** — overlapped a concurrent CPU merge; either fits |
| 07:32 | power-spike signature |

The four non-OOM events match a documented GB10 / DGX Spark defect on every criterion:

- `last -Fx` shows **no shutdown record** on any — every boot ends "still running"
- `/proc/sys/kernel/tainted` = **4096**, out-of-tree `nvidia.ko` only: the kernel never oopsed
- `/sys/fs/pstore` **empty despite a registered `efi_pstore` backend** — positive evidence: a working place to record a panic recorded nothing
- `crashkernel=1G-:0M`, kdump disabled, no dump obtainable
- no OOM, no panic, no Xid, no hung task; `clocks_event_reasons.active` = `0x0`
- always under sustained GPU load; uptimes before each: 3:33, 2:20, 3:31, 2:28

The embedded controller cuts power faster than Linux can log; the GB10 exposes no BMC, no power hwmon, and no throttle trip below 104.8 °C. Reference: [dgx-spark-hard-poweroff-fix](https://github.com/tonyd2wild/dgx-spark-hard-poweroff-fix) — community documentation, not official NVIDIA guidance, though NVIDIA has replaced units for it.

**Mitigation, applied at step 380 and made persistent** (`nvidia-smi -lgc 300,2200` plus an enabled boot service):

| | before | after |
|---|---|---|
| SM clock | 2385 MHz | 2171–2184 MHz |
| power draw | ~41 W | **~31 W** |
| GPU temp | 54 °C | 51–55 °C |
| clean step median | 30.0 s (n=57) | **30.0 s (n=38)** |

**No measurable throughput cost** — expected, since decode on a bandwidth-bound MoE is not clock-limited. An earlier +3.3% reading was n=9 and did not survive a larger sample; a −10.9% *mean* reading is an outlier artefact (a 239 s resume step in the pre-cap window), not a speed-up. There was no freeze in the ~1 h between the cap and the finish, **which is far too short to call the fix proven.** The gate runs are the real test.

---

## 6. Verified vs not

**Verified:** the run completed; both adapters match their backups bit for bit; the fingerprint held across five resumes; dev loss improved on all three splits; 908 Python tests pass; the UI typechecks, builds and passes the WCAG contrast gate; both epoch adapters are merged into the BF16 base and pushed (now public); the app ran end to end on `herald-f` (mic → Whisper → extraction → facts → contradiction → scores → confirm → relay, 21 entries reaching the ED receiver); the gate table in §8 ran on a live instance.

**Still not verified, and named as such:** the real-camera photo path (no `/dev/video*` on this box — a teammate runs it), the 30-minute soak on the shipping stack, and field audio (`~/herald-field-audio` does not exist here). Every vision number in §8 was measured on `herald-f`; because the shipping stack serves `qwen3vl-fp8` for photos instead, those numbers are being re-measured on the model that actually ships and must not be quoted until they are.

---

## 7. Order of work, as executed

1. Serve `herald-f` (epoch 2, `--quantization=fp8`, 0.35) — done, 41.1 GB.
2. App integration end to end — done, 14 facts from real speech, photo read unconfirmed with `role=photo`, relay delivered.
3. Kept-ability gates (blocking) — done, **reranking failed**.
4. Photos and POLST — done on `herald-f`; being redone on `qwen3vl-fp8`.
5. Speech against the 4B and E v2, 3× — done.
6. Latency on a quiet endpoint — pending on the shipping stack.

Epoch 1 was never gated, by §6b.

---

## 8. The gate table

Served co-resident on one GB10: `herald-f` at 41.1 GB (FP8, 0.35) and `herald-f4b-fp8` at 13.9 GB (0.12). Benchmarks
hold no weights; they call the served label over HTTP. Three runs wherever a number decides something (HARD RULE 3).

### Kept abilities — blocking (§6a). `herald-f` failed.

3 runs, byte-identical each run:

| | untuned `qwen3vl-fp8` | `herald-f` | bar | |
|---|---|---|---|---|
| rerank top1 | 0.773 = 40/52 | 0.731 = 38/52 | 41/52 | **FAIL** |
| rerank top3 | 0.864 = 45/52 | 0.788 = 41/52 | 43/52 | **FAIL** |
| refuses unanswerable | 1.000 = 7/7 | 0.571 = 4/7 | 4/7 | at the bar |
| figure nodes / edges / invented | 0.875 / 0.857 / 0.0 | 0.875 / 0.857 / 0.0 | not worse | PASS |

Honest wording: **ranking degraded slightly, refusal degraded materially (7/7 → 4/7).** Figure transcription is at
exact parity. Translation was never measured on this checkpoint and is therefore never claimed.

### Speech, held out

3 runs each on `herald-f` and E v2; 1× on the run F 4B.

| | `herald-f` | E v2 (ships) | run F 4B | bar |
|---|---|---|---|---|
| gold_v2 f1 | **0.964** (0.962–0.966) | 0.949 (0.948–0.952) | 0.914 | not worse than E v2 −0.01 |
| precision / recall | **0.972 / 0.956** | 0.961 / 0.936 | 0.923 / 0.905 | |
| role accuracy | 0.950 | **0.972** (0.972–0.976) | 0.967 | |
| **G.F.A.S.T. f1** | **0.924** (0.919–0.933) | **0.961** | 0.519 | **0.95** |
| gold_v3 every-call | **0.942** | 0.928 | 0.907 | 0.92 |
| gold_ctx dispatch | **0.938** | 0.918 | 0.898 | 0.91 |
| Mexican Spanish | **0.931** | — | 0.908 | |
| six new keys | **0.935** | — | 0.741 | 0.80 |
| adversarial seen | **20/25** | — | 16/25 | 19/25 |
| adversarial unseen | **27/40** | — | 19/40 | 24/40 |
| p95 latency | 2135 ms | 3102 ms | 2520 ms | ≤ E v2's |
| held-out wrong auto-confirms @0.8 | 11 | **1** | 10 | ≤ 1 |

`herald-f` wins nine of these and loses the two that decide the stroke screen and the confirm flow.

**G.F.A.S.T. is a genuine failure, and it is a failure of recall only.** `gfast_precision` was **1.000 in all three
runs, zero false positives** — it never scored a component wrong, it omitted components. 14 of 17 misses across the
three runs are a single key, `exam.gfast.speech`, and the same weakness shows up as `exam.race.aphasia_agnosia`
misses. It drops the language item of the stroke exam whether the finding is abnormal ("globally aphasic", "grunting,
no real words") or normal ("Speech sounds normal to me"). Downstream, by invariant 6, that renders the score
*incomplete* rather than wrong:

| score renders complete on gold_v2 | E v2 (ships) | `herald-f` | run F 4B |
|---|---|---|---|
| G.F.A.S.T. | **14/17** | 11–12/17 | 4/17 |
| RACE | **10/14** | 9/14 | 6/14 |

**Calibration was fit on dev and reported on held-out**, because fitting and reporting on one set flatters any model.
On dev `gold_v1` (286 facts, auroc 0.747) thresholds 0.8/0.9/0.99 gave 8/6/2 wrong. On held-out `gold_v2` (353 facts,
auroc 0.784) 0.8 gave **15** wrong and 0.99 gave 0 but auto-confirmed only 14.2% of facts. **No threshold reached
≤1 wrong while auto-confirming a meaningful share**, so `herald-f` would have had to ship with auto-confirm off
entirely (`HERALD_AUTO_CONFIRM=1.01`). E v2 at the configured 0.8 gives **1 wrong at 52.9% coverage**, auroc 0.804
— being re-confirmed against the current scorer on the shipping stack before it is quoted anywhere.
Recorded in `config/confirmation.yaml` under `calibration.run_f_30b`.

### Photos, measured on `herald-f`

Re-measurement on `qwen3vl-fp8` is in progress; until it lands these describe the research artifact, not the product.

| | result |
|---|---|
| synthetic `eval/photos` | f1 0.973, 1 invented, 0.93 exact-image |
| camera-on-screen, 8 stacked-degradation renders (moiré, glare, keystone, motion blur, low light, JPEG) | **48/48 values, 0 invented** |
| real phone photos, 69 images | 56/66 = 84.8% values; 40/69 = 58% of photos fully correct; **15 genuine inventions** |
| POLST `code_status`, 10 forms | 3 read, 7 empty, **0 wrong** |

The camera result says camera degradation is **not** the failure mode. The real-photo inventions are: `spo2=100`
twice from a display showing only a "still measuring" bar, and `hr=193` read off a signal-strength bar (true 85). By
device: oximeter 45/51 = 88%, Apple Watch 10/12 = 83%, thermometer 1/3. On POLST the raw model output for the seven
failures is literally `{"facts":[]}` — genuine abstention, not app-side filtering, which is the safe failure.

### Contention: one 30B does both jobs

Real speech, 3 runs: speech alone **3.28 s** (13 facts), vision alone 5.42 s, both together 7.15 s wall with the
**speech leg at 6.63 s** — contention +3.35 s, 2.02×. Still inside the 8 s capture cadence, so the queue never
overflows and a second resident model was not needed for capacity. `min_interval_s` was raised 15 → 30 from this
measurement, not from a clinical rule. Whisper warm 0.47 s, cold 4.20 s.

---

## 9. The ship decision

**Ship: Whisper + `ems-e-v2-fp8` (extraction) + untuned `qwen3vl-fp8` (photos, protocol retrieval, figures,
translation).** The §7 rollback. Reasoning in the order it decided the call:

1. `herald-f` failed a **blocking** gate. Serving it for any job leaves protocol reranking on it, and there is no
   memory for a third model to take reranking over.
2. E v2 wins the three things a medic sees: G.F.A.S.T. complete on 14/17 stroke calls against 11–12, speaker roles
   0.973 against 0.950, and 1 wrongly auto-confirmed fact against 11.
3. The untuned 30B passes reranking, figures and translation, and E v2 + one 30B is a footprint already run, so
   memory is settled by evidence rather than arithmetic.

**Rejected, and why.** `herald-f` + E v2 (a memory-neutral split) was proposed and rejected: reranking would still
sit on `herald-f`. Epoch 1 was rejected by §6b — it retained abilities *worse* (replay 0.1393 vs 0.1322), so it was
the less likely of the two to pass the same gate; it was never served and never gated. The run F 4B was rejected as
the §7 text-only fallback because it fails five speech gates E v2 passes.

**Cost of the decision:** extraction f1 0.964 → 0.949, and the sepsis flag goes from 0.889 recall to 0.111. The
second is a real product loss and is stated as a limitation below rather than hidden.

**A split stack (§7a) does not fit.** Measured: MemAvailable 40 GiB with `herald-f` + the 4B + app + Whisper
resident; swapping the 4B out returns 13.9 → 54 GiB; serving `qwen3vl-fp8` at 0.35 takes ~42 → **12 GiB left**,
below the memguard warn line of 16 and 4 above kill. Not safe.

---

## 10. Known limitations of the shipped product

These hold for the stack we ship and were measured, not assumed.

### 10a. Field-triage and sepsis criteria are not extracted reliably — by any model

`recall_floors`, `eval/gold_v3.jsonl`, 3 runs, against §6's 0.6 floor:

| | `trauma.criteria` | `infection.suspected` |
|---|---|---|
| `herald-f` | **0.25** (0.25 / 0.25 / 0.25) | **0.889** (0.889 / 0.778 / 0.889) ✅ |
| **E v2 (ships)** | **0.188** | **0.111** |
| run F 4B | 0.062 | 0.778 |
| floor | 0.60 | 0.60 |

`trauma.criteria` fails for **every model measured**, stably (0.25 in all three `herald-f` runs). This is a
capability gap, not a model choice, and it was hidden until now by the harness bugs in §10c. The misses are not
subtle: "Unrestrained driver, rollover MVC with ejection… tourniquet on at 2340… the pelvis is unstable" produced
**none** of its four criteria; "fell approximately 15 feet… pelvis unstable" produced neither.

There are also false positives. One is a factual inversion: on "**restrained** passenger t-boned on her side" the
model emitted `passenger unrestrained`. **It occurred in 1 of 3 runs, not reproducibly** — consistent with FP8
non-determinism — but an inverted restraint status is exactly the error class that would change a triage decision, so
it is recorded rather than averaged away. A second false positive, `rider separated with significant impact` on a
child who went over the handlebars, appeared in all 3 runs and is closer to a labelling disagreement than an
invention.

This matters because `trauma.criteria` drives Policy 605 and the 2021 field-triage guideline by exact value match
(`config/scores/trauma_605.yaml`).

**Product answer (owner, 2026-09-25): Herald claims no automatic field triage or sepsis criteria.** The trauma panel
is a checklist the medic confirms — criteria heard in speech appear pre-marked but **unconfirmed**, the medic taps to
confirm or add, and the score is labelled as computed from confirmed criteria only. Sepsis carries the same caveat.

### 10b. The stroke exam's language item is the weakest key

On the shipped E v2, G.F.A.S.T. renders complete on 14 of 17 stroke calls and RACE on 10 of 14. The remainder render
**incomplete**, never wrong — G.F.A.S.T. precision is 1.000 on both models. `exam.race.aphasia_agnosia` is the most
common single miss on both.

### 10c. Two harness bugs that produced false failures

Recorded because both produced confident wrong numbers that survived several readings.

**`recall_floors` measured nothing, twice over.** It pointed at `eval/gold_v2.jsonl`, which contains
`trauma.criteria` and `infection.suspected` **zero times**, so its recall could only ever be 0.0 — and `herald-f` and
the 4B "failed" it identically at 0.0, which is what gave it away. Repointing at `gold_v3` (10 and 9 occurrences,
verified) **still** returned 0.0: `eval/scoring.yaml` puts the `trauma.` and `infection.` prefixes in the `broad`
group, and `score()` keeps only keys with `group_of(key) is None`, so grouped keys are excluded from the headline
precision/recall/f1 *by design*, to keep the headline comparable with numbers published before those keys existed.
Reading headline `recall` for these keys is structurally 0.0 on **any** gold set. The gate now scores them through
`--group-gold` / `groups.broad.recall`, split per key. The 0.6 bar never moved.

**The calibration sweep reported `auroc: None`.** `eval/calibrate_confidence.py` prints a header line and then one
row per threshold; without a `select` the runner took the *last* line, the 0.99 row, which has no auroc field. Fixed
with `select: {mode: joint}`, the header's unique marker.

Earlier in the same session a third harness fault voided six gate records: `run_gates.py` invoked `run_job.py` via
its shebang, which resolved to the system `python3` instead of the environment's, so every gate died on
`ModuleNotFoundError: No module named 'yaml'`. The bogus failure records were purged rather than reinterpreted.

**The pattern worth keeping:** three separate "model failures" were harness failures, and in each case the tell was a
number that was *too clean* — 0.0 across two different models, a `None`, an identical failure everywhere. A gate that
fails identically for every candidate is measuring the harness.
