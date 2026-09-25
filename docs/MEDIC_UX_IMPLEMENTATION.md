# Medic workflow implementation — 2026-09-25

Implemented in the tushar-fs clone. The scope below describes the prototype accurately; it is not field validation.

## Available

- Primary navigation: Now, Capture, Handoff. Patient, Vitals, and Audit remain available as clinical record views. Demo controls remain behind presenter controls and shortcuts.
- Scene / Transport / Handoff workspace selection. This is screen-local navigation state, not a persisted operational timeline. New incident snapshots clear it and patient-specific acknowledgment state.
- Persistent medic and other-speaker recording, typed capture, manual structured entry, and monitor / medication bottle / form / scene photo modes.
- Manual entry uses the canonical vocabulary, units and plausibility ranges. It does not require a language model. The vehicle server must still be connected.
- Explicit recording stop, release-before-permission handling, unmount cleanup, focus-aware keyboard controls, and persistent failure messages. Browser microphone access requires localhost or HTTPS. Audio hardware and real background-noise performance still need hands-on testing.
- Clinical changes, conflicting facts, verification, and missing handoff data use distinct headings. “Mark seen” records visibility, not clinical resolution.
- Corrections validate before modifying the record, retain the rejected original and source evidence, append a confirmed medic replacement, and produce an audit entry. Outdated/repeated corrections return 409. Use manual entry for a new measurement.
- Reported patient name and patient identifier are optional canonical fields and always initially unconfirmed. The header shows incomplete identity explicitly; age/sex alone do not imply verified identity.
- The last received patient picture remains visible during a broken connection, with writes disabled and clear age information. It is memory-only, not a durable saved backup.
- Handoff leads with a structured draft of current confirmed values, capture times and unresolved fields. Treatment administration is not represented by the current schema, so the draft does not claim to be complete MIST/SBAR. A user can download this draft as text.
- Receiving-system delivery is distinguished from human acknowledgment. Packet diagnostics are collapsed. Unconfirmed destinations are not silently used for authorization.
- Vitals show the first confirmed reading, units and capture times; repeated readings add trends. Stroke score tiles are contextual to active stroke readiness.
- New incidents require explicit confirmation and a fresh dispatch reference. The existing incident is not automatically archived.

## Ambulance workspace follow-up

The default medic view has since been transformed into a cabin workspace. Continuous ambient audio replaces hold-to-record in that view, and camera evidence has an explicit preview/freeze/read/verify flow. The detailed application view remains available. See [AMBULANCE_WORKSPACE.md](AMBULANCE_WORKSPACE.md) for research, interaction decisions, safety boundaries and the field-validation plan.

## Remaining product work

These recommendations require further backend/receiver work or real-world validation and are not marked complete:

- Durable incident storage, archive/resume, close-out, authenticated staff identity, retention/access controls and durable offline capture queues.
- Persisted workflow transitions and operational pre-shift tests (microphone hardware, storage capacity, model health and monitoring).
- Receiver-side viewed / clinician acknowledgment events and ownership. The current sender cannot infer these from packet ACKs.
- Atomic medication administration and procedure events (drug, dose, route, time, administering clinician), and a clinically reviewed complete handoff template.
- CAD/ePCR/NEMSIS integration and locally approved protocol governance.
- Medic usability simulations, glove/noise/motion tests, and clinical validation. Automated tests are not evidence of field safety.

## Verification

Before the cabin revision, the production build, 30 frontend tests, 110 backend tests and theme-token contrast checks passed. The cabin revision adds capture lifecycle, UI and incident-isolation regressions; its final counts are recorded in the task handoff. Browser screenshot validation could not run because the Chromium download endpoint timed out. This limitation should remain visible in the handoff.

No shared model service, common clone, or ED incident was changed for verification. Synthetic inputs are confined to automated test contexts.
