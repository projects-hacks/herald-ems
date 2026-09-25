# Run F training report

**Status: training complete and clean. The run F 30B ships for vision, not for extraction.** 488/488 optimizer steps,
supervisor exit code 0, `DONE` written, both epoch adapters verified. The shipping stack (owner, 2026-09-25):

| job | model |
|---|---|
| speech to text | Whisper large-v3-turbo |
| speech to facts | **`ems-e-v2-fp8`** — run E v2, 4B |
| photos, the monitor, figures, protocol reranking | **`herald-f`** — run F 30B, epoch 2 |

The untuned `qwen3vl-fp8` leaves the stack; memory is unchanged, 41 GB replacing 43 GB. Extraction stays on E v2
because it wins the stroke screen, speaker roles and calibration. Vision goes to `herald-f` because it wins real
photos by a clear margin. Reranking goes to `herald-f` because it is the better of the two models we can serve, and
that costs 3 top-1 questions against the untuned baseline — a deliberate, recorded exception to a blocking gate, not a
bar that was quietly moved. §8 is the gate table, §9 the decision and what it costs, §10 the limitations that hold
regardless of which model serves which job.

**Four measurement bugs were found and fixed along the way, three of them the same root cause, and one of them
changed a number we had already reported.** They are written up in §10c rather than tidied away, because the pattern
that caught them is reusable: a gate that fails identically for every candidate, or a baseline that is suspiciously
clean, is measuring the harness.

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

### Kept abilities — blocking (§6a). `herald-f` failed on ranking.

3 runs, byte-identical each run, all on the **full 59-question set** (52 answerable, 7 unanswerable):

| | untuned `qwen3vl-fp8` | `herald-f` | bar | |
|---|---|---|---|---|
| rerank top1 | 0.788 = 41/52 | 0.731 = 38/52 | 41/52 | **FAIL, −3 questions** |
| rerank top3 | 0.827 = 43/52 | 0.788 = 41/52 | 43/52 | **FAIL, −2 questions** |
| refuses unanswerable | 0.571 = 4/7 | 0.571 = 4/7 | 4/7 | **tied, at the bar** |
| retrieval ceiling | 0.827 = 43/52 | 0.827 = 43/52 | — | identical (same index) |
| figure nodes / edges / invented | 0.875 / 0.857 / 0.0 | 0.875 / 0.857 / 0.0 | not worse | PASS |

Honest wording: **ranking lost 3 questions on top-1 and 2 on top-3; refusal did not degrade at all.** Figure
transcription is at exact parity. Translation was never measured on this checkpoint and is therefore never claimed.

**An earlier version of this table was wrong and the correction is instructive.** It reported the untuned baseline as
top1 40/52, top3 45/52 and refusals 7/7, and concluded "refusal degraded materially, 7/7 → 4/7". Those baseline
numbers were the **25-question v1 subset** (17/22, 19/22, and 3 of 3 unanswerable — that subset contains only 3 of the
7 unanswerable questions), recorded before the corpus grew to 59 questions on 2026-09-24 and then reused as the
baseline level. So a 22-question score was being compared against `herald-f`'s 52-question score. Re-derived from the
59-question dumps, refusal is **tied**. The gate's verdict never depended on this: its checks are constants written
for the 59-question set (0.788, 0.827, 0.571), and `herald-f` fails two of them either way. What changed is the story
we would have told about *how* it fails — see §10c for why this class of error kept happening.

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
| held-out wrong auto-confirms @0.8 | 3 | **1** | 2 | ≤ 1 |

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
Held out at the shipping threshold of 0.8, re-derived with the full gold (see §10c, third bug):

| | auto-confirmed | wrong | coverage | auroc |
|---|---|---|---|---|
| **E v2 (ships)** | 172 | **1** | 52.6% | 0.795 |
| `herald-f` | 206 | 3 | 59.2% | 0.773 |
| run F 4B | 161 | 2 | 50.9% | 0.846 |

`herald-f` misses the §6 bar of ≤1 at 0.8 and reaches 1 only at 0.97, where coverage falls to 26%. E v2 meets the bar
at the configured threshold, which is why it is the one with a usable auto-confirm. Recorded in
`config/confirmation.yaml` under `calibration.run_f_30b` and `run_f_4b`.

**These three numbers were first reported as 11, 1 and 10, and the 11 was an artefact** — see §10c. The corrected gap
is 3 against 1, not 11 against 1, and the earlier conclusion that `herald-f` would have to ship with auto-confirm
disabled was wrong. It does not change what ships: `herald-f` failed the blocking reranking gate and loses the stroke
screen. `herald-f`'s **dev** sweep is not quoted anywhere, because the only dev run used the flawed scoring and cannot
be re-derived — `calibration_fit` saved no dump then, and re-serving a 58 GB model to redo an informational sweep is
not a good use of the remaining time.

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

**Ship: Whisper + `ems-e-v2-fp8` for extraction + `herald-f` for photos, the monitor, figures and protocol
reranking.** The untuned `qwen3vl-fp8` leaves the stack. Decided per job, on measured numbers:

| job | winner | margin |
|---|---|---|
| speech to facts | **E v2** | G.F.A.S.T. complete 14/17 vs 11–12; roles 0.972 vs 0.950; 1 wrong auto-confirm vs 3 |
| real photos | **`herald-f`** | f1 0.727 vs 0.606; monitors 0.713 vs 0.577; pill bottles 0.753 vs 0.667 |
| camera-on-screen renders | **`herald-f`** | 48/48 vs 46/48 |
| protocol reranking | **`herald-f`**, of what we can serve | 38/52 vs E v2's 36/52 — but untuned is 41/52 |
| figures | tie | nodes 0.875, edges 0.857, 0 invented on both |

Extraction does **not** go to `herald-f` despite its higher overall f1 (0.964 vs 0.949), because f1 is not what a
medic reads: the stroke screen, the speaker labels and the confirm flow are, and E v2 wins all three.

**Reranking is a recorded exception, not a passed gate.** `herald-f` fails the §6a bars (38/52 against 41/52 top-1,
41/52 against 43/52 top-3; refusals tied at 4/7). It ships anyway because the owner weighed a measured photo win
against a measured 3-question ranking loss and took the photos. Before accepting it, E v2 was benched as an
alternative reranker — reranking is text-only, so the 4B was a credible candidate — and it scored **36/52**, worse
than `herald-f`. So `HERALD_KNOWLEDGE_MODEL` is unset and nothing recovers those 3 questions without a second resident
30B. This is written down as an exception so that nobody later reads the gate table and concludes the bar was moved.

**Rejected, and why.** Keeping the untuned 30B for vision was rejected once the real-photo gap was measured: 0.606
against 0.727, and monitors 0.577 against 0.713, on the same 97 images. Putting extraction on `herald-f` was rejected
on the stroke screen. Epoch 1 was rejected by §6b — it retained abilities *worse* (replay 0.1393 vs 0.1322), so it was
the less likely of the two to pass the same gate; it was never served and never gated. The run F 4B was rejected as
the §7 text-only fallback because it fails five speech gates E v2 passes.

**What the stack costs, stated plainly.** Protocol reranking is 3 top-1 questions worse than the untuned model could
do. The sepsis flag stays weak, `infection.suspected` recall 0.111, because that win (0.889) belongs to `herald-f` and
`herald-f` is not doing extraction. Both are limitations in §10, not footnotes.

**A two-30B split stack (§7a) does not fit, which is why these are either/or.** Measured: MemAvailable 40 GiB with
`herald-f` + the 4B + app + Whisper resident; swapping the 4B out returns 13.9 → 54 GiB; serving a second 30B at 0.35
takes ~42 → **12 GiB left**, below the memguard warn line of 16 and 4 above kill. At 0.30 each the arithmetic gets to
roughly 20 GiB free but needs `max-model-len` cut to 8192 on both and has never been started; it was not attempted
this close to the deadline.

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

**The calibration gate counted correct facts as wrong auto-confirms — the same group-gold split, third instance.**
The gate passed `--gfast-gold` but not `--extra-gold eval/gold_v2_broad.jsonl`. Eleven keys have their gold *only* in
that file (`meds.given`, `procedures.done`, `vitals.pain`, `vitals.gcs_eye/verbal/total`, `ecg.stemi_reading`,
`ecg.transmitted`, `trauma.criteria`, `trauma.mechanism`, `trauma.injuries`) and four only in the gfast file. The two
scorers disagree about what a missing gold file means, and only one of them is safe:

- `bench_extract.score()` drops keys where `group_of(key) is not None`, so a grouped key is **excluded** from the
  headline f1. Supplying `--group-gold` adds a separate score; omitting it changes nothing. Verified: held-out f1 is
  identical with and without it.
- `calibrate_confidence.correct()` judges every extracted fact against the gold it was handed and returns `False`
  when the key is absent. A missing gold file therefore counts **correct** facts as wrong auto-confirms, silently,
  and in the unsafe direction.

Cost: the gate reported E v2 at 5 wrong and `herald-f` at 11; with the broad gold they are **1 and 3**. Worse, the
published E v2 baseline of 1 *had* been measured with `--extra-gold`, so the gate had been comparing two
differently-scored numbers, and the flag was documented in `config/confirmation.yaml` the whole time — the fix was
written down before the bug was introduced. `config/gates.yaml` now passes it on both calibration gates, and
`tests/test_run_gates.py` asserts that every gate invoking `calibrate_confidence.py` supplies the gfast and broad gold
for the split it runs on, that no gate mixes the dev and held-out splits, and that `recall_floors` reads
`groups.broad.*` rather than the headline.

**The shared root cause, worth naming once.** Herald's gold is deliberately split across files so the headline stays
comparable with older published numbers. That is a good decision with a sharp edge: a bench that does not receive
every file for its split does not fail loudly, it reports a plausible worse number. All three bugs were this. The
guard is not "remember the flag" but a test that reads the gate table and checks the flags against the gold files
that exist on disk.

Earlier in the same session a third harness fault voided six gate records: `run_gates.py` invoked `run_job.py` via
its shebang, which resolved to the system `python3` instead of the environment's, so every gate died on
`ModuleNotFoundError: No module named 'yaml'`. The bogus failure records were purged rather than reinterpreted.

**The pattern worth keeping:** three separate "model failures" were harness failures, and in each case the tell was a
number that was *too clean* — 0.0 across two different models, a `None`, an identical failure everywhere. A gate that
fails identically for every candidate is measuring the harness.


---

## 11. Verification on the stack that ships

Everything here was measured against `ems-e-v2-fp8` + `herald-f` co-resident (58.6 GB of 121.6, 41.8 GB free), with
the app on `:8103`, Whisper preloaded, the ED receiver on `:8200` and the Toxiproxy link on `:9000`.

### 11a. End-to-end integration, clean

`scripts/integration_flow.py`, saved to `runs/integration/ship_stack.log`:

| step | result |
|---|---|
| egress allow-list | `allow_hosts: [127.0.0.1]`, 151 local allows, **0 denials**, 0 cloud calls, 0 refused |
| speech → facts | **14 facts in 4.04 s**, values all correct; high-confidence facts auto-confirmed, the three at 0.53–0.67 left unconfirmed |
| confirm one fact | `stroke.deficits` unconfirmed → confirmed |
| photo, monitor | **6/6 exact against gold in 5.50 s**, every fact `unconfirmed` with `role=photo` |
| POLST form | **0 facts — abstention**, which is what its gold expects |
| one-tap reading confirm | **not exercised**: needs `provenance.frame_id`, which only the camera capture path stamps |
| FHIR R4 export | `Bundle`, 6 entries (1 `Patient`, 5 `Observation`) against 9 confirmed facts |
| relay → ED | authorized to Regional, scope "Stroke alert pre-alert set", **21 fields delivered** |

The photo read is worth naming: on `cam_04_handheld_light.jpg` `herald-f` returned all six values exactly, including
`hr=96` and `spo2=94` — the pair it swaps on the six-degradation worst case (§8). It also returns a `crop` box per
reading, so each value is traceable to a region of the photo.

**Four of the "defects" this script first reported were bugs in the script, and one of those was a false pass.** They
are listed because the false pass is the instructive one:

1. It flagged the Whisper entry as a phantom model called `None` — Whisper runs in-process with no `served_as`.
2. It reported **0 facts from speech**, which was correct deduplication: it ran against the incident the soak had
   filled with the same stroke call 163 times, so every fact already existed. It now opens a fresh incident.
3. It called an empty `capture_groups` a defect. It is by design — see below.
4. It posted `/api/relay/authorize` with no body and got 422; the endpoint requires `{"destination": ...}`.
5. **The false pass:** the POLST step matched "any fact with a `photo_id`" and so reported the *previous monitor
   read's* six vitals as its own, in 0.17 s, scored them against an empty gold row, and called it a pass. Facts are
   now keyed to the `photo_id` the upload returned, a sub-0.5 s vision call is flagged as impossible, and a missing
   gold row says so instead of scoring `0/0`.

### 11b. What the one-tap reading confirm still has not verified

`POST /api/readings/{frame_id}/confirm` groups readings by `provenance.frame_id`, which the agentic capture reader
stamps on frames it takes from the camera. A manual `POST /api/photo` leaves `frame_id` and `trigger` null (verified in
the snapshot), so it forms no group. There is **no `/dev/video*` on this box**, so the path cannot be exercised here at
all. Its unit tests pass; its end-to-end behaviour is unverified and is a named gap, not a passed check.

This matters because that endpoint is the mitigation for the HR/SpO₂ label swap in §8: a swap should surface as two
implausible steps and be asked about separately. That reasoning is sound and tested at the unit level, but it has never
run against a camera.

### 11c. 30-minute soak

`scripts/soak.py`, stroke scenario on a loop, `runs/soak/ship_soak.jsonl`:

| | |
|---|---|
| duration | 1803.8 s of a 1800 s target |
| iterations / model calls | 163 / **1467** |
| model errors | **1** |
| iteration errors, relay failures | **0 / 0** |
| scenario steps | 326 done, **0 skipped** |
| latency p95 | 2633 ms overall; first 5 min 2596 ms, last 5 min 2794 ms, **drift 7.6%** against a 20% bar |
| memory | final growth **−1.03 GB** (it ended with more free than it started), peak growth 1.63 GB |
| competing jobs | none |
| `no usable frame before request expired` | **0 occurrences** — the capture-intent deadline fix holds |

`soak.py` reports `passed: false`, and it is right to, because its `model_errors_zero` check failed. **The one error
was the `/api/state` 500 in §11d**, at elapsed 195 s, inside the protocol-index build window — an app fault, not a
model fault. Every other criterion passed.

### 11c-2. Second soak, on the fixed code

Re-run after the §11d fix, `runs/soak/ship_soak2.jsonl`:

| | soak 1 (pre-fix) | soak 2 (post-fix) |
|---|---|---|
| duration | 1803.8 s | 1801.8 s |
| iterations / model calls | 163 / 1467 | 151 / 1359 |
| **model errors** | **1** | **0** |
| iteration errors / relay failures | 0 / 0 | 0 / 0 |
| scenario steps skipped | 0 | 0 |
| latency p95, first 5 min → last 5 min | 2596 → 2794 ms (+7.6%) | 3339 → 2628 ms (**−21.3%**, it sped up) |
| `no usable frame before request expired` | 0 | 0 |
| verdict | `passed: false` on `model_errors_zero` | `passed: false` on `final_memory_growth_within_1_gib` |

**The `/api/state` fix is confirmed: zero model errors across 1359 calls.** That is what this run was for.

**The remaining failure is the harness, and the evidence is unambiguous.** `soak.py` computes
`final_growth = used[-1] - used[0]` — two instantaneous samples. On this box `MemAvailable` includes reclaimable page
cache, and CUDA allocations lower it without being charged to a cgroup (AGENTS.md), so the trace is a sawtooth:
soak 2 runs 31.9 → 23.9 → 31.0 → 31.5 → 22.9 → 31.0 → 29.7 GiB, dipping and fully recovering, standard deviation
2.95 GiB. Fitting a line to all 61 samples gives the opposite of a leak:

| | slope of FREE memory | first-half median | second-half median |
|---|---|---|---|
| soak 1 | **+3.87 GiB/hour** | 30.85 GiB | 32.09 GiB |
| soak 2 | **+2.75 GiB/hour** | 29.62 GiB | 30.01 GiB |

Free memory **rose** in both runs. A 2.30 GiB "final growth" on a trace with a 2.95 GiB standard deviation is
sampling phase, not trend. **The bar has deliberately not been changed**: `soak.py` belongs to integration, and
relaxing a pass criterion at the deadline is indistinguishable from moving a goalpost. The recommendation, for whoever
owns it, is to compare the median of the last N samples against the median of the first N, or report the fitted slope,
instead of differencing two endpoints. Recorded here so the `passed: false` is not mistaken for a memory leak, and not
quietly dismissed either.

Two honest limits on this soak. It drives `/api/photo` only twice in 30 minutes, so it is a strong test of the speech
path, memory and thermals and a **weak** test of continuous monitor-watch: "0 invented monitor values" over two reads
is not a claim worth making. And it ran with no microphone, so the speech leg is text in, not audio in.

### 11d. A 500 on the medic screen, found by reading the log

`GET /api/state` returned 500 twice during startup: `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` from
`KnowledgeBase._manifest()`. It guarded for `manifest.json` being absent but not for it being **empty or half-written**,
and the file is rewritten while the protocol index builds on first start. `summary()` feeds `full_state()`, so for the
first minute or two of a cold start every poll of the screen the medic is looking at failed — the window the demo opens
in. Fixed to degrade to `{}`.

Six tests cover it and were checked against the old code: five of six fail without the fix. The first version of those
tests passed for the wrong reason — they wrote `manifest.json` to `<protocols_dir>` while the code reads
`<protocols_dir>/<county id>` — so they now assert `kb.dir` is the directory they wrote to. That is the third time
today a test or gate passed for the wrong reason, and the second time the tell was a number that was too clean.

### 11e. Latency on a quiet endpoint

`ems-e-v2-fp8`, held-out `gold_v2`, nothing else touching the GPU: **p50 1154 ms, p95 2443 ms**, first call 3035 ms,
43.4 decode tokens/s, with f1 0.948, role accuracy 0.972 and G.F.A.S.T. f1 0.961 on the same pass. Whisper adds 0.47 s
warm, 4.20 s cold. Under vision contention the speech leg was separately measured at 6.63 s (§8).

### 11f. Suites

962 Python tests and 148 UI tests pass on the merge of `origin/main` into this branch. The 968 figure in later commits
includes the six manifest tests.
