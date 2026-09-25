# Herald in the ambulance: interaction research and implementation

2026-09-25 · implementation in the `tushar-fs` clone only. This is a design hypothesis and working prototype, not a clinically validated interface.

## Product direction

Herald should feel like a quiet partner beside the patient, not a charting application that demands attention. The default view should answer four questions: Who is this patient? What is documented now? What needs my review? What is the system actually doing?

The [EMS-AI copilot concept](https://ems-ai.com/ai-copilot.html) emphasizes task-sharing, documentation during care, preservation of scene context, and clinician accountability. It is conceptual inspiration, not evidence that Herald can perform every capability described there. ECG interpretation, dosing support, prediction, and treatment recommendations are outside this implementation.

The [FDA human-factors guidance](https://www.fda.gov/medical-devices/human-factors-and-medical-devices/human-factors-considerations) specifically identifies vibration, motion, noise, lighting, and distraction as use-environment risks. Our resulting design choices—large labeled controls, fixed positions, reduced foreground detail—are design inferences that still need testing with medics.

## Information hierarchy

| Always visible or immediately reachable | One tap away | Background, never mistaken for completion |
|---|---|---|
| Patient identity and incident reference | Patient history, original sources, corrections | Local transcription and extraction |
| Latest documented vitals, units and recorded times | Trends, score inputs, missing inputs and citations | Proposed facts awaiting verification |
| Highest-priority open finding and review count | Full review queue and competing evidence | Photo interpretation after an explicit submission |
| Microphone on/off, pause, capture failures | Captured transcript and processing trace | Confirmed-fact relay after authorization |
| Vehicle-server disconnection warning | Receiving-system delivery details | Queued packets, distinct from clinician acknowledgment |

Do not display a green “all good” state merely because nothing was captured. Missing values remain dashes; an unconfirmed new value does not become a large authoritative number. No simulated ECG waveforms, invented monitoring data, or decorative clinical animations.

The implemented default is an ambulance workspace with no administrative sidebar. Four readings keep stable positions. Review, Patient, Trends and Handoff open in place. Microphone controls and the priority strip remain available on the tablet layout. On narrow phones, the dock joins document flow so it does not obscure content. The older detailed view and guided presentation remain accessible through Settings.

## Touch, drag, zoom and information buttons

- Primary controls target at least 56 CSS pixels; the phase switch uses 48-pixel-high controls. These are prototype choices, not a claim of glove usability.
- No drag-to-confirm, swipe-to-dismiss, drag-to-send, or automatic rearrangement of patient data. Accidental movement must not change a clinical fact.
- Photo drag-and-drop is available as a convenience with the same file chooser as a non-drag alternative. [WCAG dragging guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html) requires a single-pointer alternative when dragging is not essential.
- A future layout editor may allow pinning/reordering before the call, with Move up/down buttons and an explicit lock. This is not implemented; fixed positions are the current choice.
- Large view enlarges readings. Settings offers 100/125/150% text. Browser zoom/pinch is not disabled. Photo preview has explicit zoom-in/out controls from 1× to 3× and scrolling to inspect the full image. Zoom changes presentation, never the source image or extracted value. [WCAG resize guidance](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html) informs the intended 200% browser-zoom acceptance check; it has not yet been visually validated here.
- Use explanatory controls for score inputs/sources, recording behavior, and delivery semantics. A critical warning, unknown value, unverified source, or disconnected state must not be hidden behind an information icon or hover tooltip. Visible labels are preferable to a row of unexplained icons.

## Voice: start once, care continuously

Implemented flow:

`Microphone off → explicit Start → browser permission → continuous capture → short local clips → transcript → proposed facts → medic verification`

The microphone uses an AudioWorklet, which processes audio on a separate audio thread; it requires a secure browser context. See [MDN AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet). Use localhost through port forwarding, or HTTPS. No browser cloud speech service is used.

One start captures successive approximately eight-second clips without repeated button presses. A real input-level meter, listening state, processing count and pause button remain visible. Pause stops the device and submits buffered PCM. Up to two clips wait behind one request; processing overload or request failure stops recording with an explicit gap warning. There is no silent unbounded queue or automatic resend.

All ambient facts have `captured_by=other`, `role=unknown`, a speaker-unverified label and a confirmation hold. Even model-attributed medic speech cannot auto-confirm itself in this mode. Only the medic's explicit confirmation makes a fact eligible for scores/sharing. Listening does not suppress new urgent findings.

Tab hiding pauses capture. Leaving the workspace, changing patient, or losing the local-server connection stops the session and discards unsent browser buffers. Already submitted work may finish on the server. Capture is tied to its original incident, including delayed model refinement. Network failure must not be described as successful offline recording.

Limitations: this is continuous capture with batch transcription, not word-by-word streaming. Clip boundaries can split phrases; there is no validated speech segmentation, speaker diarization, overlapping-speaker handling, siren rejection, or wake-word control. Quiet/noisy clips can produce incorrect text. Never demonstrate silence as proof of reliable listening. The last sub-block of audio can be lost when stopping the audio graph. Transcription timestamps currently reflect server recording/processing, not verified measurement time. No clinical latency or accuracy claim is made.

Before field use: add timestamped streaming sessions, tested speech segmentation/context overlap with deduplication, bounded durable encrypted capture, explicit gap events, multi-speaker/noise evaluation, staff attribution, and a governed recording/consent policy. Do not implement voice commands that approve or send facts without separate explicit authorization.

## Vision: purposeful capture, not unattended surveillance

Implemented flow:

`Camera off → open viewfinder → choose source type → freeze → inspect/zoom → Read this image → proposed facts → compare with evidence → confirm`

The source types are monitor, medication label, form and scene. Preview is live but inference runs only on the submitted still. The camera turns off when details close, the tab hides, or the connection fails. A submitted photo can continue processing while another panel is open; its progress/result is available from the visual-evidence card. New-patient changes cannot redirect that result to the next patient.

Medication packaging does not prove administration, and a monitor photograph is not a live feed. Retain original evidence; never silently replace a device reading with OCR. A future continuous-camera mode needs explicit region selection, glare/blur/occlusion checks, patient association, duplicate/change detection, capture timestamps and rate limits. It must not silently infer medication administration, identity, a diagnosis, or scene facts that are not visible. Those capabilities are not implemented.

## What runs quietly, what interrupts

Extraction, trace updates and previously authorized relay can run without stealing keyboard focus or opening new panels. The attention strip remains stable while its text/count update. High-priority findings use existing deterministic rules and an assertive accessibility announcement; capture progress uses lower-emphasis status. No new audible alarms are introduced by this change. Opening the complete queue never means acknowledging a finding; confirmation and seen actions remain explicit.

The system must distinguish microphone active, clip processing, extraction finished, human verified, queued for sending, receiving server acknowledged, and receiving clinician acknowledged. Herald currently implements the first six—not the last. Connection to the vehicle server is separate from the hospital link.

## Validation and remaining product gates

Automated checks cover permission races, repeated clips, bounded backlog, stop/error handling, stale capture IDs, delayed cross-patient extraction, camera cleanup, unverified-value suppression, replay write protection, and WAV encoding. These establish software behavior under test doubles, not microphone quality, physical reach, clinical safety, or model accuracy.

Verification in this clone: 117 backend tests and 44 frontend tests pass; the production build and light/dark theme-token contrast checks pass. Port 8101 serves the rebuilt bundle and AudioWorklet asset. Browser screenshots could not run because the browser distribution download timed out. Hardware speech/camera rehearsal remains required.

Before any real patient use, run a formative study with practicing paramedics using synthetic patients in a stationary ambulance: restrained reach, dominant/non-dominant hand, gloves, daylight/night, interruptions and recorded noise. Then use a controlled simulation for motion—not an experimental UI during active care. Measure mistaken patient attribution, missed warnings, accidental confirmations, time to find provenance, recovery from silence/disconnection, and task completion without explanation. Agree acceptance thresholds with clinical governance before collecting results. Test at 1024×768, tablet landscape/portrait, 390-pixel phones and 200% browser zoom.

Highest-priority backend gaps remain durable incident storage and recovery; event-level medication/procedure documentation; verified clinician identity/access/audit/retention controls; human receiving-team acknowledgment; and CAD/ePCR integration. A modern screen alone does not close these gaps.
