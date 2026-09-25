# Tushar UI review follow-up — 2026-09-25

Branch: `feat/ui-review-gaps`, based on main `b0d264c` (including the merged patient-roster backend). Work is in Tushar's clone. The older visual redesign remains separately preserved in its named stash; this change does not restore or overwrite that work. Agentic capture remains on its separate review branch.

| Item | Implementation / remaining gate |
|---|---|
| U1 | React capture bar: medic/other push-to-talk, Space/F shortcuts, 16 kHz mono WAV, 30-second cap, typed source-tagged notes, numeric/oxygen monitor form from the contract. Fact and transcript audio playback. Camera/mic never start on mount. Fake microphone tests; physical microphone/browser permission checks remain. |
| U2 | Photo links use `/classic/capture.html`; Vite also proxies `/classic`. Existing backend route tested. No duplicate stale copy of the capture page. |
| U3 | Trauma/sepsis types, stable alert identity, red trauma HIGH, verbatim criteria and county text in React/classic. No new clinical rules. |
| U4 | Vehicle handoff page reads `/api/handoff` even before relay authorization. ED report is independently projected from already-received confirmed data, explicitly labeled as partial. Dispatch/county/timezone are not relayed: it uses the generic published-scale configuration and UTC, not a guessed county's local rules. It is not represented as the vehicle's complete report. |
| U5 | Bundled contracts refreshed; live `/api/meta` preferred with a three-second timeout and bundled fallback; fixture playback stays offline. Regression test keeps bundled key labels in step. Export disables knowledge, terminology and warm-up so it cannot load weights or build a model-backed index. |
| U6 | Patient strip mounted, add/activate API actions, active-patient relay map, patient-tagged packet log. New incident warns that it replaces the whole roster. |
| U7 | Current facts plus all medication/procedure events are deduplicated by fact ID for review and Patient view; every unconfirmed event can be tapped. |
| U8 | New incident has dispatch suggestions from checklist metadata plus free text; unspecified sends null. It never copies the previous call's dispatch. The startup-setting change remains with Vineet's backend branch. |
| U10 | Compact tablet vehicle/model/ED status; model unavailable and ED OFFLINE copy; visible toast on link-hotkey failure; no queued-key count before relay authorization. |
| U11 | ED labels from metadata with raw-key fallback, newest initial call with explicit patient selection preserved, 48 px critical values / 32 px body from UX_PLAN, patient-specific two-second NEW highlights, received contact age, record formatting and full received event history. Physical three-metre readability validation remains. |
| U13 | Intentionally pending model lock and coordination with Jenil. Existing fixture is not relabeled or represented as a fresh recording. |
| C1 | Published `feat/agentic-capture` / `88ac480`; PR creation needs authenticated GitHub access. Do not merge without reviewer approval or claim real-model acceptance. Integrating C1 must preserve the newer patient roster, request-scoped capture service and explicit mismatch Keep/Edit guards on all fact-review surfaces. |
| X3 | Shared button minimum 48 px, primary minimum 64 px; capture controls and new-incident primary follow this. |

## Safety and verification boundaries

- Capture submissions include `X-Herald-Patient`. A stale patient header returns 409 before processing. Text/audio/photo/structured capture services bind to the incident active at admission; a later roster switch cannot redirect the asynchronous result.
- Lost connection, replay, or stale state disables mutations. Releasing during a microphone-permission prompt cancels capture; late tracks are stopped. Hidden tab/window blur/patient change cancels an in-progress recording. Failed submission is shown, not retried automatically (the server may already have accepted it).
- Camera readings and other-speaker facts keep the existing confirmation policy. Monitor form entries are explicitly labeled as device readings, checked against backend vocabulary validation, and require deliberate submission.
- ED reports use only data already received through the relay; they do not call the vehicle or any model. Missing fields remain explicit. Raw unknown fields remain visible even if the report vocabulary cannot use them.
- All local verification uses fakes and CPU-only tools. No GPU jobs, model loads, fixture re-recording, or real inference acceptance is authorized until Rajeev confirms serving readiness.
- Browser binary downloads were unavailable in the prior session. Automated DOM, fake media, API, build and contrast checks are not a substitute for the hands-on microphone/tablet/ED-display test.

## Review / rehearsal checklist after the gate

Local verification: 414 backend tests passed, one skipped; 46 UI tests passed; production build, both-theme contrast checks, classic/ED JavaScript syntax checks and whitespace checks passed. These are implementation checks, not a real-model or clinical acceptance result.

1. Verify the immediate U1–U3 beats on React; keep `/classic/` available as fallback until the physical microphone test passes.
2. Test microphone permission denial, release-before-permission, pointer cancellation, key release and patient switch. Confirm audio plays for the correct patient and source.
3. Create two synthetic patients; activate each, confirm an older dose, inspect packet patient labels and ED selection. Check that roster replacement requires the New incident dialog.
4. Check a red trauma and sepsis scenario against the county text. Read both report formats aloud, explicitly noting that ED only has received data.
5. Review at tablet width and on the actual ED display at three metres. Check focus order, zoom, target size and status visibility.
6. After model lock, coordinate U13 with Jenil and record at the demo time of day; preserve model/version and timing evidence. Run C1 real-model acceptance separately after its serving gate.
