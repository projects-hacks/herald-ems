# Run F training report

**Status: training complete and clean.** 488/488 optimizer steps, supervisor exit code 0, `DONE` written.
Both epoch adapters exist and are verified. **No gate has run yet, so nothing here says the model ships.**

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

## 1. Dev loss, and why epoch 2 ships

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

**Verified:** the run completed; both adapters match their backups bit for bit; the fingerprint held across five resumes; dev loss improved on all three splits; 813 Python and 121 UI tests pass; the UI typechecks, builds and passes the WCAG contrast gate; both epoch adapters are merged into the BF16 base and pushed to private repos (13 shards, 57.9 GiB, index present).

**Not verified — everything that matters for shipping.** No gate has run. The highest-risk item is not a gold score at all: **no 30B has ever run through the app**. Mic → Whisper → extraction → facts → confirm → relay → ED screen, plus the photo and POLST vision paths and Spanish, are all untested against this model. A failure there changes what we ship regardless of gold numbers.

A **4B run F fallback** is merged and pushed and enters the gate table as its own level, so a text-only option exists if the 30B fails.

---

## 7. Order of work

1. Serve `herald-f` (epoch 2, `--quantization=fp8`, ~0.35).
2. **App integration: one real end-to-end flow.** Report every integration bug — prompt and parse failures, timeouts, malformed JSON, the vision path, Spanish.
3. **Kept-ability gates** on that instance (blocking; they decide the ship question).
4. Photos and POLST.
5. Speech, 1×, against the 4B run F.
6. Latency measured separately on a quiet endpoint, so the deck's numbers are honest.

Epoch 1 is not in this list, by §6b.
