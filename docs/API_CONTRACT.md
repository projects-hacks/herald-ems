# Runtime contract

The authoritative snapshot types are in `ui/src/lib/types.ts`; HTTP and WebSocket routes live in `herald/api/routes/` and `herald/api/routes/agentic_capture.py`. This reference retains the implemented contracts from the former UX plan; completed screen plans and build proposals have been removed.

## Interface and interaction constraints

- One React medic application at `/`; its source is `ui/src`, and `ui/dist` is ignored build output. Missing builds return 503 with build instructions. API routes and `/capture.html` still work. `/classic/` redirects to `/`, and `/classic/capture.html` redirects to `/capture.html`.
- The ED receiver is a separate service for receiving staff. The standalone camera page is an optional input device. `/monitor.html` displays synthetic equipment readings and never submits patient facts.
- Live snapshots replace server state; expansion, navigation, theme and text size are local UI state. Fixture playback never submits mutations. Heartbeat staleness blocks writes. An action reports success only after the server responds.
- Observations are not a live physiological monitor. Pending readings do not replace the last confirmed reading. Only confirmed facts drive scores and leave the vehicle after sharing authorization.
- Operational text has a 13 px floor at default scale; controls have 48 px targets and primary confirmation actions 64 px. Colors accompany words/icons, timers are monospace and numbers tabular. Text scaling and reduced motion remain available. These design constraints do not establish field usability or standards compliance.
- Clinical change precedes positive stroke screens, contradictions and routine confirmation in the review queue. Source disagreements require an explicit choice, with nothing preselected. Model availability failure is a prominent urgent state.
- Transcript rows update in place; new entries wait behind an explicit jump while older entries are being read. Provenance describes recorded evidence, not model reasoning.

### Continuous workspace and journey contract (2026-09-25)

The medic workspace's **Camera → Monitor watch** uses the existing S9 endpoints below, always with the active `incident_id`. It remains mounted across internal care-page navigation. It requests camera access only on Start, allows at most one unacknowledged JPEG, and stops on tab hide, patient change, disconnect or explicit Stop. `/capture.html` remains the standalone option.

- Fact provenance gains optional `observed_at: ISO datetime`. For selected camera frames this is the vehicle's frame-receipt timestamp, not extraction completion and not an inferred administration time. `Fact.ts` remains record time. Old fixtures may omit `observed_at`.
- `Snapshot.changed[].times` uses `provenance.observed_at` where available, otherwise record time. Confirmed-history handoff points include time and unit through the configurable `point_template` in `config/handoff.yaml`; report sources add `observed_at` and `frame_id`.
- Full relay timeline entries gain optional `o: ISO datetime` for observation time. Full packets gain optional `lkw_at: ISO datetime` derived from the vehicle's confirmed LKW clock. Critical packets and their byte budget are unchanged. No raw media or unconfirmed facts are added to relay.
- ED state carries nullable `lkw_at`. A changed or withdrawn LKW invalidates prior elapsed metadata; a full sync replaces it. ED uses only absolute, zone-qualified timestamps for elapsed time, displaying “elapsed not received” otherwise. Empty full timelines replace previous history.
- ED metadata key entries include optional `unit`. Journey display uses received confirmed history, labels UTC timestamps, and explains that newer critical fields may have arrived separately from the latest full history. The received-data report preserves observation time.
- Capture timeline updates existing rows in place; new captures wait for an explicit jump. Visible evidence is retained while being read even when it leaves the server's rolling transcript window; patient changes reset it.

### UI review contract additions (2026-09-25)

Integration with ambient capture and patient roster: both `X-Herald-Patient` and existing multipart `incident_id` guards remain supported. Request-scoped capture retains camera listeners and ambient confirmation holds. Roster changes clear automatic camera work and ROI. Generic fact correction returns409 for an unresolved medication-label mismatch; only the explicit capture verification endpoint resolves it. These additive checks also apply when using the ambulance workspace.

- React text, audio and device-reading capture sends optional `X-Herald-Patient: <incident id>` to existing `/api/transcript`, `/api/audio`, `/api/facts` (and supported photo capture). Mismatch returns409 before processing. Each admitted request binds its capture service to the original patient throughout asynchronous extraction. This header is a race guard, not authentication.
- Live label loading prefers `/api/meta`; bundled `/contract/*.json` stays the offline/fixture fallback. Numeric monitor controls accept vocabulary `int`/`float` types and use their labels/units.
- React uses existing `/api/patients` add and `/{id}/activate` endpoints; `Snapshot.relay.patients[active_patient].sync` is authoritative in multi-patient mode. Packet log entries carry `patient?: string`; pending rows also carry `patient?: string`. Legacy single-patient snapshots fall back to `relay.sync`. No sent/queued badge is shown before authorization.
- Trauma/sepsis alerts carry `{type:"trauma_alert_criteria"|"sepsis_prenotification", label:string, level:string, score:string, criteria:string[], county_rule?:string[], county?:string}`. Red trauma is HIGH; other listed criteria alerts are CHECK. Criteria and county text are displayed verbatim.
- Vehicle read-aloud view uses existing `/api/handoff?format=<id>`; results are invalidated on patient change and hidden while stale. It is available independently of relay authorization.
- **ED receiver only:** `GET /api/meta` returns `{keys: Record<string,{label:string,unit?:string}>, display:{critical_keys:string[],critical_px:number,body_px:number,highlight_ms:number,report_county:string,report_timezone:string}}` from reviewed vocabulary/scores and `config/ed_display.yaml`. `GET /api/handoff/{patient_id}?format=<id>` returns the existing report shape plus `scope:string`, computed solely from received confirmed fields/timeline. Missing patient →404; unknown format →400. It is explicitly a received-data projection, not the vehicle's full report; vehicle dispatch/county/timezone are not inferred. The receiver uses generic published scales and UTC, explicitly labeled, with no guessed county-local rule. Neither endpoint starts models or reaches the vehicle.

### Record tabs: per-point confirmation and level-valued severity (2026-09-26)

- `Snapshot.changed[]` gains optional `confirmed: boolean[]`, one per point in `series`: whether that reading is confirmed. The Trends & scores tab draws a waiting point hollow and labels it "to confirm", and never shows it as the vital's value. Additive; older snapshots omit it and every point is drawn as before.
- `severity` (config/vital_ranges.yaml) now also covers `vitals.gcs_total`, `vitals.gcs_motor` and the level-valued `vitals.consciousness` (ACVPU). A band may match levels with `{in: [...], severity}` instead of numeric bounds. The shape is unchanged: `severity` is still `"abnormal" | "critical"` or absent.

### Speech clips the speech model says are not speech (backend, 2026-09-25)

`POST /api/audio` passes every clip through three gates read from Whisper's own signals before any words reach the record (`herald/models/stt_gates.py`; thresholds and the allowed languages are content in `config/stt.yaml`, citing openai-whisper's `transcribe()` defaults and the measurements in `docs/MODEL_PLAN.md` §0k "Speech gates"): the probability of `<|nospeech|>` at the first decoder step, the language that step hears (English and Spanish are read; the clip is also dropped when the probability mass on those two languages is below the configured minimum, which is how large-v3-turbo tells noise from speech since it never predicts `<|nospeech|>`), and the zlib compression ratio of the decoded text (a repetition loop). Live on 2026-09-25 a silent ambient clip came back as an echo of the priming prompt's example values and a blood pressure nobody said was extracted; the prompt is now vocabulary only.

- A dropped clip returns `200 {"transcript": null, "facts": [], "stt": {"text": "", "chunks": [], "seconds", "ms", "language": "ru" | …, "dropped": "no speech" | "language" | "repetition loop", "signals": {"no_speech_prob", "language_prob", "read_language_prob", "compression_ratio"}}}`: no transcript entry, no extraction call, no activity line. The recording is kept as evidence like any other clip. `signals` is an API field for diagnosis; it is never put on a transcript entry or the medic's screen.
- A kept clip's transcript entry `stt` (and `trace.heard.stt`) gains `language: string | null`, the language the clip was heard in, as Whisper names it (ISO 639-1).
- `GET /api/telemetry` gains `stt_dropped: {reason: count}` for the session (the dropped clips' audio still counts in `calls.stt` and `stt_audio_min`).
- The ambient speaker label is `"Speaker not identified"` (was `"Ambient audio · speaker unverified"`; `herald/api/capture.py` `AMBIENT_SPEAKER`, `ui/src/lib/format.ts` `UNIDENTIFIED_SPEAKER`). A fact's source chip shows it as it is; the activity feed's heard line omits it: `Heard “…”`, never `Heard Speaker not identified: “…”`.

### S9 agentic capture contract (2026-09-25)

Camera capture is off by default. `HERALD_CAPTURE_SOURCE=off|browser|replay:<folder>` and `HERALD_CAPTURE_AUTO=0|1` configure initial state; `HERALD_CAPTURE_CONFIG` names reviewed content under `config/`. USB/local camera support remains optional and is not enabled. The policy, gate, intervals, storage limits and trigger keys live in `config/capture.yaml`.

| Boundary | Contract |
|---|---|
| `WS /ws/frames` | One same-origin browser source per incident. Binary JPEG, longest side ≤1280 px and encoded size ≤1 MiB. Process/reply at most `fps_in` (default 1 Hz). Reply `{accepted, gate: {sharp, changed, bright, passed, reason, usable} | null, error?: string}`. Extra frames are dropped, never queued without a bound. Patient change requires explicit reconnect. |
| `GET /api/capture/status` | `CaptureStatus` below. `watching` requires recent accepted input, not merely the switch being on. |
| `POST /api/capture/auto` | `{on: boolean}`; returns status. Off invalidates pending work/results and clears frame buffers. A submitted model call cannot be preempted, but its result is discarded. Turning on an off source selects browser input. |
| `POST /api/capture/roi` | `{x0,y0,x1,y1,target?: "monitor"}`, finite normalized coordinates with positive area. Returns status; invalid rectangle →422. ROI changes invalidate old buffered work. |
| `DELETE /api/capture/roi` | Clears the incident's monitor ROI; monitor watch remains disabled without one. |
| `POST /api/capture/now` | `{mode?: "monitor"|"pill_bottle"|"form"|"scene"}` →202 and status. Defaults to monitor with ROI, label otherwise. Queues best recent frame or next frame, expires after ten seconds. Bypasses quality and automatic rate limits, not single-flight or speech priority. |
| `POST /api/capture/verify/{fact_id}` | `{action:"keep"}` or `{action:"edit",value:<complete dose record>}`. Returns fact view; 404 other incident/missing dose, 409 closed/invalid mismatch, 422 malformed request. Edits append a medic-confirmed replacement and reject the old event; Keep confirms the original explicitly. Both retain an audit trace. Generic `/facts/{id}/confirm` returns409 for unresolved mismatches. |

```ts
interface CaptureStatus {
  auto: boolean; source: string; fps_in: number; incident_id: string;
  sees: "off" | "watching" | "reading";
  roi: {x0:number; y0:number; x1:number; y1:number} | null;
  last: {ts:number; trigger:string; mode:string; reason:string; facts:string[]; photo_id:string|null} | null;
  counts: {frames:number; gated:number; captured:number; stored:number};
  error: string | null; pending: number;
}
interface Verification {
  status: "match" | "mismatch"; label_drug: string; photo_id: string | null;
  resolution: "kept" | "edited" | null;
}
```

Snapshot gains `capture: CaptureStatus`. Fact views gain nullable `verify: Verification`; provenance gains optional `trigger`, `frame_id`, and `auto`. Selected-frame trace entries retain `captured_by="camera"` and add `trigger`, `reason`, `frame_id`, nullable `photo_id` and fact IDs. Stored evidence is retrieved through the existing `/api/photo/{photo_id}`; `auto_*` IDs resolve inside `photo_dir/auto`. No file exists when no usable fact/flag results or redaction fails. Old fixture snapshots omit the additive fields; the UI must tolerate this.

Patient guard: `auto`, `roi` and `now` POST bodies accept optional `incident_id: string`; DELETE ROI accepts the same query parameter. The shipped UI always sends it. A stale identity returns409 without changing the new incident. Verification IDs are resolved only in the current incident. A configured replay source rejects browser sockets to prevent mixed views. Switching patients also disables capture and clears ROI. Speech-to-text and extraction counters both block capture admission; already-running vision cannot be preempted.

Visual semantics: “Herald sees” off/watching/reading is technical status, not an alarm. Reading may use a reduced-motion-aware pulse. A drug-label mismatch is a steady caution/check card with spoken drug, label, evidence and explicit Keep as said/Edit actions. A match verifies ingredient only—not dose, route, patient, timing or administration. Verify-intent output never enters `meds.list`. Camera facts always start unconfirmed. The confirmation hold is applied synchronously to the crew dose before the asynchronous label check, so it cannot leave while the check waits. Match/unreadable never auto-confirm it.

The standalone camera accessory uses `/capture.html`. Continuous camera requires localhost or HTTPS, explicit permission, visible preview and a stop control. It offers drag ROI and numeric-coordinate alternatives; a one-shot file input remains available. Camera close/tab hide/network failure stops the source; no automatic permission restart. Privacy is an in-memory ring buffer plus redacted used-evidence files, not continuous video storage. Face detection is fallible and requires spot checks. No field-safety or real-model acceptance claim is implied by fake tests.

### Relay consent scope (2026-09-25)

`POST /api/relay/authorize` (`{destination: string}`) already derived the medic-facing scope label from whichever checklists are actually open (`herald/api/context.py` `pre_alert_scope`, never a client-supplied string; see `test_relay_scope_is_derived_from_the_active_checklist_not_the_client_label`). What was missing: the relay send itself ignored that scope and always sent every tier. Fixed in `herald/relay/tiers.py` (`RelayScopes`) + `config/relay.yaml` `scopes`/`default_scope`: a same-purpose alert pre-alert (stroke/trauma/sepsis/stemi — the checklist alert ids in `config/checklists.yaml`) now authorizes only relay tiers 1-3 (critical facts, score changes, current vitals/exam); tiers 4-5 (arrival logistics, demographics) flow only once no specific alert checklist is open, under the broader `patient_update` (default) scope, which is the unrestricted, every-tier send.

- `authorized` (in relay status / `POST /api/relay/authorize`'s response) gains `alert_ids: string[]` alongside the existing `destination`, `scope` (label, unchanged) and `at`. Empty when no alert checklist was open at authorization time (the broad scope). Old persisted/fixture snapshots without it behave as empty (unrestricted), matching prior behaviour.
- `sync`/`pending` in relay status, and everything the relay actually sends, are filtered by the ceiling of the authorized `alert_ids`; nothing new here for the UI to read, but a "critical only" view of `sync`/`pending` while a stroke/trauma/sepsis/STEMI alert is the open scope is expected, not a bug.

### Batch confirm: capture groups, one tap per reading (2026-09-25)

Cuts the tap burden without auto-confirming anything. One monitor frame yields HR/BP/SpO2/RR at once; the medic now confirms the *reading*, not each value. Engine: `herald/core/corroboration.py` (`CorroborationRules`, `BatchConfirmation`); content: `config/corroboration.yaml` (risk tiers, plausible-step deltas, medic-facing wording). No confidence gate and no auto-confirm anywhere in this path — a reading is only ever flagged for individual review or left for a one-tap batch; only the medic's tap moves a fact to `confirmed`.

- Snapshot gains `capture_groups: CaptureGroup[]`, one entry per frame that still has an unconfirmed reading, oldest first.
- `POST /api/readings/{frame_id}/confirm` — confirms every batchable reading of that frame in one call. 404 if the frame has no unconfirmed reading left (unknown id, or already fully confirmed). 409 if the incident has ended. Readings the rules flag (a jump past the configured plausible step, the first reading of a key when `first_reading: individual`, a held fact, an unresolved label mismatch, a contradiction, or any non-batchable key/source) are left `unconfirmed` and reported back in `individual` with why; they still need `/api/facts/{id}/confirm` or `/api/facts/confirm`.
- Lever 2 (corroboration): only monitor-sourced vitals (`vitals.*`, `captured_by` camera/device) ever batch. A reading within its configured plausible step of the previous reading of that key is batchable; a reading that jumps past it is flagged, not auto-confirmed and not batched — same intent as the `significant_change` deltas in `config/trends.yaml`, kept as separate numbers so the two can be retuned apart. Medications, allergies, code status and identity/triage facts are always individual, whatever their source.

```ts
interface CaptureGroup {
  frame_id: string; trigger: string | null; photo_id: string | null; ts: string;  // ISO
  batch_fact_ids: string[];   // one POST confirms all of these
  individual: {id: string; key: string; label: string; reason: string | null}[];
}
```


## `/api/telemetry` contract (backend-provided, U15)

The backend builds this endpoint; the frontend only reads it. Values are sampled in a background task every 2 s and cached, so the endpoint is cheap.

```jsonc
GET /api/telemetry  →  200
{
  "ts": "2026-09-24T21:40:00.123Z",
  "window_s": 10,                                   // window for the per-second rates
  "model": {
    "served_name": "omni",                          // llm.model_name()
    "reachable": true,                              // the metrics fetch succeeded
    "requests_running": 0, "requests_waiting": 0    // vllm:num_requests_running / _waiting
  },
  "tokens": {
    "server_prompt_total": 556702,                  // vllm:prompt_tokens_total (every client of this model server)
    "server_generation_total": 25357,               // vllm:generation_tokens_total
    "generation_per_s": 41.2,                       // Δ server_generation_total / window_s; null until 2 samples
    "prompt_per_s": 812.0,
    "herald_prompt": 18230,                         // sum of `usage` from Herald's own LLM/vision calls
    "herald_completion": 1904,
    "since": "2026-09-24T20:05:11Z"                 // Herald process start
  },
  "latency_ms": { "ttft_p50": 185, "e2e_p50": 790, "e2e_p90": 1978 },   // from histogram buckets; may be null
  "power": {
    "gpu_w": 28.2,                                  // nvidia-smi --query-gpu=power.draw.instant
    "gpu_w_avg": 27.9,                              // power.draw.average
    "scope": "GPU only (nvidia-smi). SoC and module power aren't exposed on this box.",
    "sample_every_s": 2
  },
  "energy": { "gpu_wh": 12.34, "since": "2026-09-24T20:05:11Z" },   // trapezoidal integral of gpu_w
  "cost": {
    "local_usd": 0.0019,                            // gpu_wh / 1000 × usd_per_kwh
    "cloud_equiv_usd": 0.43,                        // herald_prompt × in + herald_completion × out, per million tokens
    "net_savings_usd": 0.428,                       // cloud_equiv_usd − local_usd
    "assumptions": {
      "usd_per_kwh": 0.15,                          // as shown on HP's ZGX console at the event; no public URL
      "cloud_usd_per_mtok_in": null,                // backend sets these, with a citation:
      "cloud_usd_per_mtok_out": null,
      "cloud_price_ref": "provider · model · date · URL"   // required whenever the prices are set
    }
  },
  "cloud_ai_calls": 0,                              // the same counter as snapshot.counters.cloud_ai_calls
  "errors": []                                      // e.g. ["metrics unreachable", "nvidia-smi missing"]
}
```

**Where the numbers come from (verified on this box, 2026-09-23).**
- **ZRT proxy metrics:** `GET http://127.0.0.1:8080/metrics/<served-name>` (e.g. `/metrics/omni`) returns vLLM's Prometheus metrics through the ZRT proxy [63].
  - Available names include `vllm:prompt_tokens_total`, `vllm:generation_tokens_total`, `vllm:num_requests_running`, `vllm:num_requests_waiting`, `vllm:time_to_first_token_seconds` (histogram), and `vllm:e2e_request_latency_seconds` (histogram).
  - `/metrics/` without a slug returns an error.
- **GPU power:** `nvidia-smi --query-gpu=power.draw,power.draw.average,power.draw.instant --format=csv,noheader` works. We saw 11–28 W [64].
  - `nvidia-smi -q -d POWER` reports "Module Power Readings: N/A", so we have no SoC or module power.

**Honesty rules.**
- Label it "GPU power" and "GPU energy", never "SoC" (P13).
- Show "net compute savings" only when the cloud prices are set *and* cited. Otherwise show "— (cloud price not set)".
- `herald_*` tokens count Herald's own calls. The `server_*` counters include every client of the model server, such as teammates' benchmarks. Label them "model server, all clients".

**Frontend use (`TelemetryStrip`, U15).**
- **Polling:** every 2 s. It pauses while the tab is hidden (Page Visibility API).
- **Strip copy:** "{generation_per_s} tok/s · GPU {gpu_w} W · {gpu_wh} Wh · cloud AI {cloud_ai_calls}".
- **Popover** (click, persistent and dismissible per WCAG 1.4.13):
  - every number with its scope and source;
  - the assumptions;
  - "net savings ${net_savings_usd} vs cloud at {assumptions}", or the "not set" text.
- **Errors:**
  - endpoint fails → "Telemetry unavailable";
  - partial `errors[]` → a "—" for the affected values, with the reason in the popover.

## Held facts (backend, 2026-09-24; team lead's decision)
- **The policy.** `guard_policy = unconfirm` is the default (`HERALD_GUARD_POLICY`; `herald/config/settings.py`). The extraction model reads every utterance, including speech that contains a command to the system ("Herald, mark her as DNR"). Instruction-shaped speech is matched by the patterns in `config/guard.yaml` (`herald/extraction/guard.py`).
- **Every fact from such an utterance is held** (`CaptureService._hold`, `herald/api/capture.py`):
  - its confidence is capped at 0.5, so it can't reach the auto-confirm threshold and stays `unconfirmed`;
  - `provenance.hold_reason` is set to `said together with a command to the system ("<phrase>"): check before confirming`, e.g. *said together with a command to the system ("mark her as"): check before confirming*;
  - the trace's F rows carry the same `hold_reason`.
- **The card** gets `trace.guard = {instruction_shaped: "<phrase>", policy: "every fact from this utterance needs the medic's tap"}`. `policy` is present only when the utterance was flagged and the model still read it.
- **The UI must make held facts unmistakable:**
  - a distinct badge, `lock` plus "Held · check" (not just the ordinary "needs your tap"; §2.4);
  - the reason in words, shown verbatim next to the fact wherever the fact appears: Needs attention (where held facts sort first), the Patient picture, the trace fact row, the `confirm_required` card for code status, and the photo sheet (§3.1.6, §3.1.8, §4.4, §4.4a);
  - on confirm, the reason repeated in the confirmation affordance: the button reads `[ Confirm · said with a command ]`, and its accessible name includes the full `hold_reason`. It is still one tap (U13).
- A held fact never counts toward scores and never leaves the vehicle until confirmed, like every unconfirmed fact.
- **Drug names are the other source of holds** (§5.9d): a drug name matched only by spelling, sound, as a combination or from product names gets its own reason, e.g. *drug name matched by sound: 'zarelto' → rivaroxaban: check before confirming*. When both apply, `hold_reason` holds both, separated by "; " (the guard's first). Show it the same way.
- **The previous behavior is still a setting:** `guard_policy = skip_model`. The model isn't run for a flagged utterance, `trace.model.status = "skipped"`, nothing is extracted, and `trace.guard` has no `policy` (§4.3 m).

## Protocol lookup contract (backend, 2026-09-24)
- `GET /api/protocols` → `{ready, building?, county, sections, missing[], review_required[], last_sync, destination_audit_ok, documents[{id, title, effective}], destination_audit[{service, document[], config[], match, only_in_document[], only_in_config[]}]}`. It returns 503 while the index builds, and 404 when lookup is off.
- `GET /api/protocols/search?q=<text>&k=5` → `{query, answerable: true|false|null, reranked, results[{doc, title, section, heading, page, text, parents[], effective, text_layer_uncertain, score}]}`.
  - Show `text` verbatim with "{doc} §{section}, page {page}, effective {effective}".
  - `answerable: false` → "The county documents don't cover this."
  - `text_layer_uncertain` → offer the page image ("the printed page may differ from the extracted text").
- `GET /api/protocols/{doc}/page/{n}` → PNG of the printed page.
- `POST /api/protocols/sync` → `{checked, updated[], errors[], at}`. `POST /api/protocols/{doc}/reviewed` clears the review flag after a person checks the county config.
- The snapshot's `protocols` block is the same shape as `GET /api/protocols` without the audit detail. Show "Protocol updated: review county settings" while `review_required` is non-empty.
- **Search panel (UI, 2026-09-25):** `ui/src/features/protocols/ProtocolSearch.tsx`, `<ProtocolSearch open query? onClose />`, a right-side sheet with types `ProtocolAnswer` / `ProtocolPassage` in `lib/types.ts`.
  - Opened from the sidebar's "Protocols" row (explain view) and the "Protocols" button in the ambulance workspace header (medic view). A `query` opens it already searched, e.g. from the RACE / G.F.A.S.T. "County destination policy ▸" link (§3.1.7).
  - Each passage: heading, the citation line above, parent headings, then `text` verbatim; the first passage is open, the rest collapsed.
  - States: "Searching the county documents…", then "Still waiting for the server…" after 2 s; 404 → "Protocol lookup is off on this vehicle."; 503 while building → "The county documents are still loading. Try again in a moment."; any other failure → "The Herald server didn't answer. Try again."; replay → off.
  - `answerable: false` still lists the closest passages, under "The county documents don't cover this. Closest passages:".
  - Typed search only; asking by voice comes later.

## County alert checklists and criteria scores (backend, 2026-09-24)

Herald keeps a checklist and the county's own criteria for trauma, sepsis and STEMI calls, the same way it does for strokes. Every criterion and checklist item quotes its source; the research behind them is `docs/research/county_protocols_2026-09.md` (§5 trauma, §6 sepsis, §7 STEMI, §9 proposed checklists), and every county quote was re-read from the archived PDFs on 2026-09-24. Herald shows criteria and what is missing. It never recommends a treatment or a destination; the only destination text it shows is the county's own rule, quoted with its section.

**Where it lives**

| Part | File | Tests |
|---|---|---|
| Rule types (one small function each) | `herald/scoring/rules.py` | `tests/test_criteria_rules.py` |
| Criteria engine (`kind: criteria`) | `herald/scoring/criteria.py` | `tests/test_criteria_rules.py` |
| Santa Clara Policy 605 Trauma Alert criteria | `config/scores/trauma_605.yaml` | `tests/test_county_scores.py` |
| Santa Clara 700-A04 sepsis pre-notification | `config/scores/sepsis_700a04.yaml` | `tests/test_county_scores.py` |
| National 2021 field triage (same engine, shape unchanged) | `config/scores/field_triage.yaml` | `tests/test_scores.py` |
| Checklist items (record fields, alternatives, scores, conditions) | `herald/checklists/items.py` | `tests/test_criteria_rules.py` |
| County overrides for any alert, triggers | `herald/checklists/engine.py` | `tests/test_county_alerts.py` |
| Default checklists (counties without their own) | `config/checklists.yaml` | `tests/test_contract.py`, `tests/test_county_alerts.py` |
| Santa Clara checklists and quoted rules | `config/counties/santa_clara.json` → `alerts` | `tests/test_contract.py`, `tests/test_county_alerts.py` |
| Relay tiers for the new scores | `config/relay.yaml` | `tests/test_county_alerts.py` |
| UI contract (`scores.json`, `checklists.json`) | `herald/api/contract.py` | `tests/test_contract.py` |

**Rule types.** A rule reads confirmed values and is **met**, **not met**, or **unknown** (an input is missing, never guessed). A list value that wasn't described (a pelvic fracture nobody mentioned) is unknown, never "no".

| Type | Met when | Used for |
|---|---|---|
| `below`, `above` | value < or > the threshold | 605 J (motor GCS), 605 X.7 weeks, 700-A04 HR, RR, EtCO2 |
| `outside` | value < low or > high | 605 K (RR < 10 or > 29), 700-A04 temperature |
| `between` | low ≤ value ≤ high (either bound optional) | 605 R age 0-9, 602 adult age, the pregnancy-item display rule |
| `room_air_below` | SpO2 below the threshold on room air; unknown on oxygen | 605 M |
| `sbp_by_age` | SBP below the age band's limit (each band has its own code and text) | 605 N.1-N.3 |
| `hr_above_sbp` | HR > SBP from a minimum age | 605 N.4 |
| `motor_gcs_below` | motor GCS below the threshold; without a motor score, a GCS total settles it only by arithmetic (15 means motor 6; 7 or less means motor 5 or less; 8-14 stays unknown) | 605 J |
| `present` | the key has a value that isn't one of the listed negative words ("none") | 605 X.1 (anticoagulant), 700-A04 suspected infection, 605 applicability |
| `present_prefix` | any key with the prefix has a value | the stroke checklist opens once a stroke exam starts |
| `contains` | a list key holds the value (the text names it) | 605 A-I, L, O-W, X.2, X.6, major burn |
| `one_of` | a single value is one of the listed values | the pregnancy-item display rule (sex) |
| `record_has` | a record key holds a record whose field is one of the values | 605 I (tourniquet, wound packing), L (BVM, CPAP, supraglottic airway, intubation), X.7 (CPR or defibrillation) |
| `count_at_least`, `all_of`, `any_of` | at least n, all, or any of the nested rules; decided as soon as the answer can't change | 700-A04 §1.4 (infection and 2 of 4 SIRS), 605 I, L, R, X.7 |

**A criteria result** (`CriteriaResult`, §5.6):
- `met`: a hit in a group that counts (`red` or `yellow`; sepsis `notify`). A met criterion counts even while other inputs are missing.
- `complete`: every required input is present. Policy 605's required criteria are J, K, M, N.1-N.3 and N.4 (the vital signs); 700-A04's is §1.4 with every input under it, so a sepsis result can be met and still incomplete ("EtCO2 (not measured)").
- `level`: the first counting group with a hit; `flagged`: a hit in any group, including `consider` and `burn`.
- `applies`: false while the precondition isn't met. Policy 605 §II.B applies to "injured patients", so until a mechanism, an injury or a trauma criterion is described the trauma score says so and flags nothing: a hypotensive medical patient is never a Trauma Alert.
- `criteria[]`: every criterion with its state, the county's words (`label`), the values that decided it (`finding`), and for an unknown vital sign what is missing (`needs`). Nested rules are in `parts[]`.

**Policy 605 (`trauma_605`, Santa Clara, effective 2025-04-01, AO 2025-005 PDF pages 25-27).**

| Group (`groups[].id`) | Counts as a Trauma Alert | Criteria | From which facts |
|---|---|---|---|
| `red` (HIGH) | yes | A-I High Risk Injury Pattern | `trauma.criteria` values; I also from `procedures.done` tourniquet or wound packing |
| `red` | yes | J-N Mental Status and Vital Signs | J `vitals.gcs_motor` (or the total, by arithmetic), K `vitals.rr`, L `trauma.criteria` or respiratory support in `procedures.done`, M `vitals.spo2` + `vitals.on_oxygen`, N.1-N.3 `vitals.sbp` + `patient.age`, N.4 `vitals.hr` > `vitals.sbp` from age 10 |
| `yellow` (MEDIUM) | **yes**: Policy 602 §VI.C makes a Yellow hit a Trauma Alert in Santa Clara | O, P, Q, R (with age 0-9), T, U, V, W | `trauma.criteria` values |
| `consider` (LOW) | no: "should be considered", EMS judgement | X.1 (anticoagulant), X.2, X.6, X.7 (pregnant beyond 20 weeks with CPR or defibrillation recorded) | `meds.anticoagulant`, `trauma.criteria`, `patient.pregnancy_weeks`, `procedures.done` |
| `burn` (MEDIUM) | no: §III major burn criteria send the patient to a burn center, not a §II.B criterion | III.A | `trauma.criteria` "major burn" |

Age banding: read literally, N.2 "Age 10-64 years" and N.3 "Age older than 65 years" leave age 65 in no band. 605 §II.A says the county's criteria are the ACS national guideline, which uses "age ≥ 65", so Herald puts 65 in N.3. Suspected findings count: the county words several patterns as "suspected" (B, C, D, E, F).

**700-A04 (`sepsis_700a04`, Santa Clara, effective 2026-01-01).** §1.4: "Advanced notification to hospital of suspected sepsis patient if two or more SIRS criteria are met". Herald evaluates it as a suspected infection (`infection.suspected`) **and** at least 2 of: temperature below 96 °F (35.56 °C) or above 100.4 °F (38.0 °C), HR > 90, RR > 20, EtCO2 < 25 mmHg. `vitals.temp` is Celsius to 0.1 °C, so 35.5 °C counts and 35.6 °C (96.1 °F) doesn't. EtCO2 is often not measured (capnography is required only with an airway adjunct, 700-S04 §3.2, and a colorimetric device gives no number, Policy 302): it then shows as "not measured", never as "not met". **Wording:** the county says "advanced notification", and Policy 501 names only Trauma, Stroke and STEMI Alerts, so every screen says "Sepsis pre-notification", never "Sepsis Alert".

**Checklists.** Defaults are in `config/checklists.yaml`; the active county's `alerts` section overrides any alert field by field (label, source, items, triggers, `open_on`, unknowns, quoted rules), and the county's `stroke.checklist` still replaces the stroke items. A checklist opens on dispatch or chief-complaint words (`triggers`), on facts (`open_on.facts`, rules over every value including ones waiting for a tap), or on a score with any criterion hit (`open_on.scores`).

| Checklist | Santa Clara (county override) | Other counties (default) | Opens on |
|---|---|---|---|
| `trauma` "Trauma Alert" | Mechanism of injury (501 §IV.E.1; 700-A16 §6.1) · Trauma criteria (Policy 605) `@trauma_605` (501 §IV.E.2; 602 §VI.C) · GCS `vitals.gcs_total\|vitals.gcs_motor` (700-S04 §2.2; 700-A16 §6.3) · Systolic BP (605 N.1-N.3) · Heart rate (605 N.4) · Respiratory rate (605 K) · SpO2 (605 M) · Anticoagulants (605 X.1; 700-S06 §3.3) · Pregnancy (weeks), when relevant (602 §VI.C.4; 605 X.7) · Destination (602 §VI.C.2-3, Table B) · ETA (501 §III.A.1.b) | the same shape with `@field_triage` (national 2021) instead of `@trauma_605` | words (fall, MVC, crash, GSW, stabbing, assault, pedestrian, struck, ejected, rollover, burn, trauma, injury); Santa Clara: the trauma score has any criterion hit; default: any `trauma.*` fact |
| `sepsis` "Sepsis pre-notification" (default "Suspected sepsis") | Suspected infection (700-A04 §1.4, §4.1) · Temperature (§1.3.1) · Heart rate (§1.3.2) · Respiratory rate (§1.3.3) · EtCO2, note "not measured" (§1.3.4) · Systolic BP (§1.1) · Mental status `vitals.consciousness\|vitals.gcs_total` (700-A10 §4.1) | the same without EtCO2, plus `@news2` (Surviving Sepsis Campaign 2026: use a standard screening tool en route) | words (fever, sepsis, septic, infection, pneumonia, UTI, cellulitis); `infection.suspected` present |
| `stemi` "STEMI Alert" | 12-lead reads "STEMI" or "Acute MI Suspected" (700-A08 §3.2; 700-M09 §4.9.1) · Symptom onset (§1.2, §6.1) · First 12-lead time (§6.2) · 12-lead transmitted to the STEMI center (§1.4, §3.2.2; 700-M09 §4.9.1.1) · Systolic BP (501 §III.A.4) · Allergies (501 §III.A.3) · Time of aspirin administration `meds.given[drug=aspirin]`, note "not recorded" (700-A08 §6.3, a documentation element) | unchanged (symptom onset, 12-lead time, 12-lead attached, allergies, anticoagulants, blood pressure) | words (chest pain, STEMI, heart attack, ACS, ST elevation; Santa Clara adds substernal, chest pressure or tightness, impending doom from 700-M09 §3.1); Santa Clara: `ecg.stemi_reading` true |
| `stroke` | unchanged: the county's `stroke.checklist` (G.F.A.S.T.) | unchanged (RACE) | words; a stroke exam has started |

- **Record-field items:** `meds.given[drug=aspirin]` is done when any confirmed `meds.given` record has drug "aspirin" (the labeling guide's generic name), pending when one waits for a tap, missing otherwise. The label is the county's documentation element, "Time of aspirin administration": a record of what was given, never a prompt to give it.
- **Alternatives:** `vitals.consciousness|vitals.gcs_total` is done when either is confirmed.
- **Score items:** `@trauma_605` is done when the score is complete or met (once a criterion is met the Trauma Alert answer is known); pending when a fact waiting for a tap would complete it.
- **Conditional items:** the pregnancy item is listed unless the patient is known to be male or outside ages 10-55. This is Herald's own display rule (design decision, stated in `config/checklists.yaml`), wider on purpose than the CDC reproductive-age band of 15-44, so a patient who could be pregnant is never skipped. In the contract it has `conditional: true`.
- **Moved:** in Santa Clara, "Anticoagulants" left the STEMI item list for its "not yet asked" list, because no county STEMI document asks for it (research §7.2).

**Snapshot.**
- `scores` holds every published score plus the active county's own criteria: `trauma_605` and `sepsis_700a04` exist only while Santa Clara is active.
- `readiness[]` entries carry `source`; items may carry `note`. `needs_attention` entries may carry `note`.
- `alerts[]` gains `trauma_alert_criteria` and `sepsis_prenotification` when the score is met: `{type, score, label, level, criteria[], county_rule?[], county?}`. For a Trauma Alert, `county_rule[]` quotes Policy 602: §VI.C.2 (adult, age 15 and over) or §VI.C.3 (pediatric, under 15 per §VI.H), §VI.C.4 (pregnant beyond 20 weeks: "the closest trauma center with an approved Level III Neonatal ICU (Stanford Hospital or Santa Clara Valley Medical Center)"), and §VI.D when a major burn is described.

**Relay.** `score.trauma_605` and `score.sepsis_700a04` are tier 1 ("the receiving team needs this before arrival"; Policy 501 §IV.E.2 requires a Trauma Alert report to state the Policy 605 criteria). What is sent:
- trauma: the met codes by group, e.g. `RED N.3; YELLOW O, U` (about 20 bytes); `no Policy 605 criterion met` once complete with no hit; nothing while undecided or not applicable;
- sepsis: `met (infection: urinary; T 38.6 °C; HR 112; RR 24)`; `not met` once complete; nothing while undecided.
Like every relayed key, a line the ED already acknowledged stays on the ED screen if the result later becomes undecided (for example a rejected blood pressure). A later complete result replaces it.

**What the county documents say that Herald can't represent faithfully** (no fact in `config/vocabulary.yaml`; a vocabulary change is the owner's decision):
- **605 S** "Vehicle telemetry data consistent with severe injury": no `trauma.criteria` value.
- **605 X.1, second half** "or with bleeding disorders": no key for a bleeding disorder, so only anticoagulants are computed.
- **605 X.3** "EMS provider judgment to transport patient to a trauma center": the medic's judgement, not a fact Herald derives.
- **605 X.4** hanging or mechanical asphyxiation in cardiac arrest with suspected head or neck injury, and **X.5** unwitnessed drowning with suspected head or neck injury: no values.
- **605 X.7** "uterine fundus palpated at or above the umbilicus" and "does not meet obvious death criteria": Herald reads the weeks as said and "in cardiac arrest" from CPR or defibrillation in `procedures.done`.
- **605 N**: the county text leaves age 65 in no band (above).
- **700-S06 §1.11** (a fall more than 72 hours ago with no Red criterion is not a Trauma Alert): needs a time of injury; the research recommends reusing `symptom.onset`, which is not decided yet, so it is not applied.
- **700-A08 §6.4** "Time of STEMI Alert notification to hospital" and **§1.1** "within 10 minutes of patient contact": a relay send time and a patient-contact time, not spoken facts; not checklist items.
- **Policy 501 §II.B vs §II.C** (which channel a sepsis notification uses) is an inference from Policy 501 and flagged for review; Herald shows no channel.
- **AO 2025-006 and AO 2025-007** amend Policy 602 and are not archived; the destination rules quoted above are from the 2025-04-01 text.

## Medication and allergy coding contract (backend, S6, 2026-09-24; MODEL_PLAN §0j)
**What gets coded.** The keys are listed in `config/terminology.yaml` `keys`: the items of `meds.list` and `allergies`, the `drug` of every `meds.given` record, and `meds.anticoagulant`. Nothing else ever has a `code`.

**Values.**
- A drug name that matched RxNorm becomes RxNorm's ingredient name, lowercase ("Eliquis" → "apixaban"). A combination uses RxNorm's name, ingredients in alphabetical order joined by " / " ("Percocet" → "acetaminophen / oxycodone", "Tylenol 3" → "acetaminophen / codeine").
- A name that matched nothing keeps the spoken text.
- An allergy to a class of drugs ("sulfa", "penicillin") keeps its words; only its `code` says the class (below).

**`code`** on `FactView` and `TraceFact` (`FactCode`):
- a FHIR-style `Coding` `{system, code}`:
  - RxNorm: system `http://www.nlm.nih.gov/research/umls/rxnorm`, code the RxCUI;
  - a class allergy: system `http://hl7.org/fhir/sid/icd-10-cm`, code one of NEMSIS eHistory.06's ten Z88 codes (Z88.0 penicillin, Z88.2 sulfonamides, …).
- For list keys, `code` is a list with one entry per item, in the same order. `null` (or a `null` entry) means not coded.
- `meds.given` and `meds.anticoagulant` carry a single `Coding` or `null`.

**`provenance.normalized[]`** records, per name: `said`, `value`, `system`, `code`, `method` and `score`.

**Methods, and which ones hold the fact for a tap:**

| `method` | Meaning | Held |
|---|---|---|
| `exact` | the name, or a product name with its number ("Tylenol 3") | no |
| `class` | a class allergy named by its NEMSIS label or ICD-10-CM substance ("sulfa") | no |
| `combination` | parts joined into an RxNorm combination ("ipratropium-albuterol") | yes |
| `contained` | a word RxNorm uses only inside product names ("nitro spray" → nitroglycerin) | yes |
| `fuzzy` | matched by spelling | yes |
| `phonetic` | matched by sound | yes |
| `class_fuzzy` | a class allergy matched by spelling ("penicillins") | yes |
| `unresolved` | no match; the text is kept | — |
| `ambiguous` | no match; the text is kept | — |

A held fact has `provenance.hold_reason`, e.g. *drug name matched by sound: 'zarelto' → rivaroxaban: check before confirming* (§5.9a). It stays unconfirmed whatever its confidence.

**UI**
- Fact details show, e.g., "Eliquis → apixaban · RxNorm 1364430", or "sulfa · ICD-10-CM Z88.2 (sulfonamides)".
- A name that isn't coded shows as said, with "not found in RxNorm".
- A held drug fact shows its reason like any held fact (§5.9a). Never show a non-exact match as more certain than the fact's status.

**Classes.** A class drug appears under both keys: an anticoagulant is also in `meds.list`. A drug outside the class (e.g. clopidogrel) is never `meds.anticoagulant`. Classes are config files (`config/terminology/anticoagulants.yaml`).

**Health.** `GET /api/health` returns `terminology: {rxnorm_release}`, or `null` when the index isn't built; then nothing is coded. The stack view shows "Drug names not coded".

**Where coding happens.** In the model extractor, the photo reader and `POST /api/facts`, so every path into the patient picture is coded the same way. The relay sends values only; `code` stays on the vehicle.

## Handoff report contract (backend, 2026-09-24)

Herald writes the handoff the paramedic reads to the receiving ED, by radio or at the bedside, and that the ED screen can show. No model writes any of it. Every line is a template from `config/handoff.yaml`, filled with confirmed values and with the scores the Projector already computed. Nothing in the report is a recommendation.

**Where it lives**

| Part | File | Tests |
|---|---|---|
| Formats, lines, wording, sources (content) | `config/handoff.yaml` | `tests/test_handoff.py` (loads the real file for every county) |
| Builder: picks the format, builds sections, gaps, unconfirmed list | `herald/reporting/handoff.py` | `tests/test_handoff.py` |
| Line kinds `fact`, `events`, `score`, `trends` (a registry; a new kind is a new class) | `herald/reporting/lines.py` | `tests/test_handoff.py` |
| Confirmed facts, provenance, units and value wording | `herald/reporting/view.py` | `tests/test_handoff.py` |
| Plain-text rendering | `herald/reporting/text.py` | `tests/test_handoff.py` |
| Content checks at startup (unknown keys, scores, checklists, template fields refuse to start) | `herald/reporting/config.py`, `herald/api/context.py` `build_handoff` | `tests/test_handoff.py` |
| `GET /api/handoff`; snapshot `handoff` summary | `herald/api/routes/handoff.py`, `herald/api/context.py` `full_state` | `tests/test_handoff.py` |
| Score input keys (which facts a score line came from) | `input_keys()` on every engine, `CriteriaScore.criteria_keys()` | `tests/test_handoff.py` |

**Sources for the formats.**
- **Primary: Santa Clara County EMS Policy 501, Hospital Radio Reports** (effective 2025-01-01; `data/protocols/santa_clara/archive/501_hospital-radio-reports_eff-2025-01-01.pdf`, re-read 2026-09-24).
  - §III.A sets the standard report's contents, in this order: unit ID, ETA, age, sex; the primary impression and the chief complaint; pertinent history, medications, allergies and findings; vital signs; and the treatment provided.
  - §IV.D: a Trauma, Stroke or STEMI report "shall start with a clear statement indicating what type of alert applies".
  - §IV.E: a Trauma Alert report adds the mechanism of injury and the Policy 605 anatomic and physiologic criteria.
- **MIST/ATMIST**: Wood K et al., Emerg Med J 2015;32(7):577-581 (PMID 25178977).
- **Allergies, medications and background after MIST**, as in IMIST-AMBO: Iedema R et al., BMJ Qual Saf 2012;21(8):627-633.
- **SBAR**: Leonard M et al., Qual Saf Health Care 2004;13(Suppl 1):i85-i90.

**Formats and how one is chosen.** The first rule in `select` whose checklist is open wins. Otherwise the report uses `default`.

| `format.id` | Chosen when | Sections, in order |
|---|---|---|
| `mist` "MIST (trauma)" | the `trauma` checklist is open (dispatch or complaint words, trauma facts, or the county's trauma criteria) | `opening` (alert statements, SALT triage category, unit, ETA, destination, age and sex, time of injury (ATMIST's T), primary impression, chief complaint), `mechanism` (M), `injuries` (I: injuries found, then each Policy 605 criterion met; `field_triage` in counties without their own), `signs` (S: airway, BP, HR, RR, SpO2 with air or oxygen, GCS or ACVPU, temperature, glucose, pain, EtCO2, 12-lead with its territory, NEWS2, trends), `treatment` (T: this crew's), `before_arrival` (care given before this crew arrived), `history` (allergies, anticoagulant, medications, code status, pregnancy), `other` (scene notes) |
| `medical` "SBAR (medical)" | otherwise | `opening` (alert statements, SALT triage category, unit, ETA, destination, primary impression), `situation` (age and sex, chief complaint, symptom onset; last known well, onset witnessed and deficits while the stroke checklist is open; suspected infection; mechanism, time of injury or injuries if any), `background`, `assessment` (the same signs, plus the stroke scales while stroke is open and the sepsis criteria while sepsis is open), `treatment` ("T: Treatment given", which replaces SBAR's R because Herald never recommends), `before_arrival`, `other` |

`?format=` overrides the choice. `selected_by` says why the format was picked: `checklist:<id>`, `default`, or `request`.

**Alert statements (501 §IV.D).** The medic declares the alert. The report's opening states which county criteria or readings are met, from confirmed facts, so the medic can say it:
- "Trauma Alert criteria (Policy 605) met" (or "Field triage (2021) met");
- "12-lead reads STEMI, inferior (700-A08 §3.2)" (the territory when it was stated);
- "G.F.A.S.T. 4 of 4" or "RACE n of 9" when positive;
- "Sepsis pre-notification criteria met (700-A04 §1.4)".

The report never says "Trauma Alert", "Stroke Alert" or "STEMI Alert" on its own authority.

**The keys approved on 2026-09-24** (`config/vocabulary.yaml`), and where each goes in the report:

| Key | Where it goes | Wording | Required |
|---|---|---|---|
| `impression.primary` (501 §III.A.2; NEMSIS eSituation.11; the medic's words, never Herald's diagnosis) | opening, both formats (MIST: after age, sex and time of injury; SBAR: after the ETA) | "Impression: hip fracture after fall" | yes: "Primary impression: not yet known" |
| `trauma.injury_time` (ATMIST's T) | MIST opening, right after age and sex (ATMIST's order); SBAR situation when said | "Injured at 14:02" | MIST only: "Time of injury: not yet known" |
| `airway.status` (501 §III.A.5) | first line of the signs (MIST S, SBAR A) | "Airway: patent with adjunct" | no |
| `ecg.territory` | with the STEMI reading, in the opening statement and in the signs | "12-lead reads STEMI, inferior, lateral, transmitted"; alone "12-lead territory inferior" | no (it never covers the "12-lead reads STEMI" gap) |
| `triage.category` (SALT; `require_tap`) | opening, right after the alert statements, once tapped | "Triage: immediate (SALT)" | no; until tapped it is only in `not_yet_confirmed[]` |
| `before_arrival` on `meds.given` and `procedures.done` (NEMSIS eMedications.02, eProcedures.02) | its own `before_arrival` section, after the crew's treatment, both formats | "Before arrival: naloxone 2 mg IN, by fire; c-collar, by fire." | no; an empty section is left out of the text |

**Rules the builder keeps** (AGENTS.md invariants 3-6):
- **Confirmed only.** A line shows only confirmed values. A fact waiting for a tap (a photo reading, another speaker, low confidence, held, a contradiction, code status) is listed in `not_yet_confirmed[]` by key and label with its fact ids, **never with its value**. `differs: true` when it disagrees with the confirmed value the report shows. That list is the only place such a fact appears, so the report is safe to show on the ED screen.
- **Missing shown as missing.** A required line with no confirmed value becomes `{status: "missing", text: "<label>: not yet known"}` in its place (e.g. "Last known well: not yet known" on a stroke call). It stays silent while a value for it waits for a tap, because it has been heard, not missed. Some lines are required only while a checklist is open: glucose and last known well for stroke, temperature and suspected infection for sepsis, anticoagulant for trauma, stroke and STEMI, symptom onset for STEMI.
- **Checklist gaps.** Every open checklist's missing item that no line covers is listed once, in `not_yet_known[]`, with its note (e.g. "EtCO2 (not measured)").
  - A line covers only the keys it actually shows. "12-lead transmitted" does not cover "12-lead reads STEMI".
  - Record-field items (the time of aspirin, 700-A08 §6.3) are never listed. The treatment list is the record of what was given, and a report must never read as a prompt to give something.
- **Scores with their source.**
  - A complete banded or item score reads e.g. "NEWS2 7, high risk (RCP 2017)" or "G.F.A.S.T. 4 of 4 (700-A13 §2.3)".
  - An incomplete one shows what is missing and **no partial total**: "NEWS2 incomplete: Respiratory rate, Consciousness, Temperature not yet known (RCP 2017)".
  - A criteria score lists each met criterion in the county's words, e.g. "Policy 605 Red N.3 Age older than 65 years: Systolic BP is less than 110 mmHg (SBP 84, age 72)". It reads "no criterion met" once complete, "undecided" otherwise, and nothing while it doesn't apply.
  - Every score line has `source`, the score definition's full citation.
- **Treatment.** Every confirmed `meds.given` and `procedures.done` event is listed in the order recorded. The same event said twice is one line carrying both fact ids. Fields that weren't recorded are left out, never filled in, e.g. "aspirin 324 PO, by crew" when no unit was said, or "fentanyl 50 mcg IV at 14:22, by crew". A section with no treatment reads "none recorded" (`status: "empty"`).
- **Before arrival.** A dose or procedure with `before_arrival: true` goes in the `before_arrival` section, never in the crew's treatment. One with `before_arrival` false or not stated counts as the crew's: Herald never infers timing from who gave it. The split is an `events` line option, not a special case. `where: {before_arrival: true}` keeps records whose field has that value, and `where_not` drops them; a field that wasn't recorded matches no value.
- **Deterministic.** The same facts give the same JSON and the same text. `as_of` is the time of the last fact, not the time of the request.

**Types** (add to `ui/src/lib/types.ts`):

```ts
export interface HandoffSource {                 // one fact behind a line
  fact_id: string; key: string; role: Role; speaker: string | null; captured_by: CapturedBy;
  time: string;                                  // local "HH:MM" when it was recorded
  ts: string; audio_id: string | null; photo_id: string | null; extractor: string | null;
}
export interface HandoffLine {
  kind: "fact" | "event" | "score" | "trend" | "missing" | "empty";
  status: "confirmed" | "missing" | "empty";
  text: string;                                  // as read aloud; wording and units from config
  keys: string[];                                // vocabulary keys shown ("@<score>" for a score line)
  fact_ids: string[];                            // link to the audio clip or photo via FactView.provenance
  sources: HandoffSource[];
  source?: string;                               // score lines: the score's citation
}
export interface HandoffSection {
  id: string; label: string;                     // e.g. "mechanism", "M: Mechanism"; "before_arrival", "Before arrival"
  say_label: boolean;                            // false for the opening (read without its label)
  source: string | null;                         // which Policy 501 / MIST / SBAR item it implements
  lines: HandoffLine[];
}
export interface HandoffGap { key: string; label: string; note?: string; checklists: ChecklistId[]; text: string }
export interface HandoffWaiting { key: string; label: string; fact_ids: string[]; differs: boolean }  // no value, on purpose
export interface HandoffReport {
  format: { id: "mist" | "medical"; label: string; title: string; source: string };
  formats: { id: string; label: string }[];
  selected_by: string;                           // "checklist:trauma" | "default" | "request"
  incident: { id: string; dispatch: string | null; started: string; ended_at: string | null;
              media_disposal: MediaDisposal | null };
  county: { id: string; name: string };
  as_of: string;                                 // time of the last fact (ISO)
  open_checklists: ChecklistId[];
  sections: HandoffSection[];
  not_yet_known: HandoffGap[];
  not_yet_confirmed: HandoffWaiting[];
  text: string;                                  // plain text: the title, then one line per section, then the two lists
}
export interface HandoffSummary {                // snapshot.handoff
  format: "mist" | "medical"; label: string; selected_by: string;
  lines: number; missing: number; unconfirmed: number;
}
```

**Endpoint.** `GET /api/handoff` returns a `HandoffReport` for the current incident. `?format=<id>` returns HTTP 400 for an unknown format; the message names the valid ones.

**Settings.** `HERALD_UNIT_ID` (e.g. "Medic 25", 501 §III.A.1.a) opens the report with "<unit> en route". Without it the line is left out.

**Screen note: ED handoff page** (`ui/src/pages/HandoffPage.tsx`, frontend-owned):
- **Placement.** Add a "Report" card next to the relay figures. The header shows `format.title` and a two-way switch, MIST / SBAR, that re-fetches with `?format=`.
- **Sections.** Render them in order, each with its label, and one line per row. Show `status: "missing"` rows in the missing style (P2, gap-first), never as values. A row's `sources` give the chip "said 14:22 · medic", and tapping it opens the fact's audio clip or photo (`FactView.provenance`).
- **Lists.** Show `not_yet_known[]` and `not_yet_confirmed[]` below the sections, under their own headings. A `not_yet_confirmed` item links to the fact on the NOW screen to confirm it. Never show a value there.
- **Read-aloud.** Offer `text` in a monospace block with a copy button for the radio report.
- **Refresh.** Re-fetch when `snapshot.handoff` changes. The summary counts are cheap enough to badge the tab, e.g. "3 not yet known".
- **Wording.** Don't reword lines in the UI: they are the county's words and the config's templates.

## FHIR R4 export contract (backend, X2, 2026-09-25)

`GET /api/handoff/fhir` returns the current incident's confirmed record as a FHIR R4 `Bundle` (`type: "collection"`), for a records request or a receiving system that wants structured data instead of the read-aloud report. Same confirmed-only guarantee as `/api/handoff` and the relay (AGENTS.md invariant 4): a fact waiting for the medic's tap never appears, whatever resource type it would otherwise become. Engine: `herald/reporting/fhir.py` (`FhirExport`); coding content: `config/fhir_codes.yaml` (LOINC for vitals/age, a local `http://herald.local/fhir/scores` system for Herald's own computed scores — text-only, since they aren't LOINC panels). No SNOMED CT or other UMLS-licensed vocabulary is used; drug/allergy `Coding` is only ever the RxNorm/ICD-10-CM codes `herald/terminology/` already resolved onto the fact (`config/terminology.yaml` systems), passed through unchanged — this export invents no coding of its own.

| Resource | From | Notes |
|---|---|---|
| `Patient` (one, id `patient-<incident id>` with `_` → `-`) | `patient.name`, `patient.identifier`, `patient.sex` | `gender` mapped to the FHIR value set; no `birthDate` (only a spoken age is known) |
| `Observation` (vital-signs) | every confirmed reading of `vitals.*` in `config/fhir_codes.yaml` `vitals` | one Observation **per confirmed reading**, not just the latest — the trend, like the NOW screen's movement view |
| `Observation` (social-history) | `patient.age` | LOINC 30525-0 "Age"; one per confirmed reading |
| `Observation` (survey) | `snapshot()["scores"]`, i.e. computed from confirmed facts only | one per score once it's `complete` (`relay_text` non-null, the same gate the relay uses); `valueString` is that same line |
| `MedicationAdministration` | `meds.given` (each confirmed dose event) | `medicationCodeableConcept.coding` present only when the fact already carries an RxNorm `Coding` |
| `AllergyIntolerance` | the latest confirmed `allergies` list, one resource per item | coding present only when the fact already carries one (RxNorm or the NEMSIS drug-class ICD-10-CM code) |
| `Condition` | `impression.primary` (`verificationStatus: unconfirmed`, noted as the crew's stated impression, not a diagnosis) and each confirmed `trauma.injuries` item (`verificationStatus: provisional`) | text-only `code`; Herald never diagnoses (AGENTS.md invariant 3) |

**Known limitation, flagged for a clinical/coding review pass, not silently shipped as verified:** the LOINC codes in `config/fhir_codes.yaml` are the standard, commonly used codes for these panels, assembled from memory for this change and not re-checked against a live LOINC lookup in this session. Give them one review before this export is relied on outside a demo.

**Test:** `tests/test_fhir_export.py` — full bundle shape across every resource type, unconfirmed facts (camera-sourced, low-confidence, and a rejected fact) proven absent, existing RxNorm/ICD-10-CM coding passed through unchanged, and the live endpoint.

### The handoff as a FHIR document (2026-09-25; changes the default of `GET /api/handoff/fhir`)
`GET /api/handoff/fhir?type=document|collection&format=<id>`. **`type=document` is now the default**; `type=collection` returns the resources above unchanged (the previous default). `format` is the same override as `/api/handoff` (e.g. `mist`, `medical`); unknown `type` or `format` → 400. The NOW screen's "Export (FHIR)" link therefore downloads the document.

The document is a FHIR R4 `Bundle` of `type: "document"` (https://hl7.org/fhir/R4/documents.html): `identifier` `{system: http://herald.local/fhir/handoff-document, value: "<incident id>/<report as_of>"}`, `timestamp` (assembly time), every entry with a `fullUrl` `http://herald.local/fhir/<Type>/<id>`, and every `reference` resolving inside the bundle. Engine: `herald/reporting/fhir_document.py` (`FhirDocument`, over `HandoffBuilder` + `FhirExport.sourced`); codes and wording: `config/fhir_codes.yaml` `document`.

| Entry | Contents |
|---|---|
| `Composition` (first) | `type` LOINC 34133-9 "Summary of episode note" (`text` = the report title, e.g. "Medical handover (SBAR)"); `status: preliminary` and no `attester` (assembled from confirmed facts, not signed by the crew); `subject`, `encounter`, `date` = report `as_of`, `author` = the Device. `section`: "How this document was assembled" (with the format's citation), then **the report's own sections in order** (`title` = section label, e.g. "S: Situation"; `text` = XHTML list of the report lines plus the section's source, with `<b>` on a line that states a confirmed value of a `document.emphasis` key (vitals, allergies, anticoagulant) or an emphasis score that is positive/met (never on a "not yet known" line, a trend, or an incomplete/negative score); `entry` = the resources behind those lines, scores via their `@<score>` keys), then "Not yet known" and "Not yet confirmed, left out of this report" (names only, never values) when non-empty |
| the collection's resources | exactly `FhirExport.sourced()` — the same confirmed-only resources as `type=collection` |
| `Encounter` | `class` v3-ActCode `FLD` "field"; `status` `in-progress` until the incident is ended, then `finished` with `period.end`; `type[0].text` "EMS response: <dispatch>"; `hospitalization.destination.display` = the confirmed `transport.destination` |
| `Device` | "Herald", `note` "Herald on <HERALD_UNIT_ID>" |
| `Provenance` (one per resource built from facts) | `target` the resource; `recorded` its latest fact time; `agent`: `assembler` = the Device, `informant` = who said it (`"<speaker> (<role>)"`), `verifier` = who tapped confirm, from the incident audit log (absent when the policy confirmed the medic's own speech on ingest: no tap is claimed); `entity` `source` = "audio clip <id>" / "photo <id>" (ids only, never media) |

**Resource ids are now valid FHIR ids** (`[A-Za-z0-9.-]{1,64}`) in both types: Herald's underscores become hyphens, e.g. `patient-inc-03f1ac7a3c` (was `patient-inc_03f1ac7a3c`, which FHIR rejects).

**Codes checked 2026-09-25** against loinc.org/34133-9, the FHIR R4 ActEncounterCode value set and the R4 provenance participant type value set (citations in the config). LOINC 67796-3 (NEMSIS v3 patient care report) was deliberately not used: this document is not a NEMSIS PCR. Not yet checked with the official HL7 FHIR validator.

**Test:** `tests/test_fhir_document.py` — document rules (identifier, timestamp, Composition first, unique fullUrls, valid ids), every reference resolves, Composition sections equal the report's (SBAR and MIST), waiting facts named but never valued, Provenance informant/verifier/source, Encounter and Device, and the endpoint's `type`/`format` handling.

**What the report can't represent yet.** The five gaps listed in the first version (time of injury, before arrival, airway status, primary impression, 12-lead territory) were closed by the keys approved on 2026-09-24 (table above). They reach the report only once the extraction model emits them; until then they show as "not yet known" where required.

## Overheard speech: the check step and what is kept (2026-09-25)
- A transcript entry's `trace.model.discarded` lists the facts the extraction model proposed from room-microphone
  speech (`captured_by: other`, role unknown) that the check step (`herald/extraction/verify.py`, prompt
  `config/prompts/fact_verify.md`, the knowledge model) found the words do not state about the patient:
  `[{key, value, why}]`, or `[{error}]` when the check could not run (every proposal then stays, unconfirmed).
- Overheard speech that leaves no fact and asked for no protocol is removed from `transcripts` once extraction
  finishes, and its audio is deleted; it is counted in `/api/telemetry` `stt_dropped["nothing clinical"]`.
  The medic's own and typed words are always kept.
- A monitor-camera frame that gives no new reading no longer adds a transcript entry; it is counted in
  `capture.last` and `capture.counts`.
- A transcript entry carries `asked: true` when its words asked for a county protocol.

