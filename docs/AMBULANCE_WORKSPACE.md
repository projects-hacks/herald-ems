# Herald in the ambulance: interaction research and implementation

2026-09-25 · implementation in the `tushar-fs` clone only. This is a design hypothesis and working prototype, not a clinically validated interface.

## Product direction

Herald should feel like a quiet partner beside the patient, not a charting application that demands attention. The default view should answer four questions: Who is this patient? What is documented now? What needs my review? What is the system actually doing?

The [EMS-AI copilot concept](https://ems-ai.com/ai-copilot.html) emphasizes task-sharing, documentation during care, preservation of scene context, and clinician accountability. It is conceptual inspiration, not evidence that Herald can perform every capability described there. ECG interpretation, dosing support, prediction, and treatment recommendations are outside this implementation.

The [FDA human-factors guidance](https://www.fda.gov/medical-devices/human-factors-and-medical-devices/human-factors-considerations) specifically identifies vibration, motion, noise, lighting, and distraction as use-environment risks. Our resulting design choices—large labeled controls, fixed positions, reduced foreground detail—are design inferences that still need testing with medics.

## Information hierarchy

| Always visible or immediately reachable | One tap away | Background, never mistaken for completion |
|---|---|---|
| Patient identity, crew label and call start | Patient history, original sources, corrections | Local transcription and extraction |
| Latest documented vitals, units and recorded times | Trends, score inputs, missing inputs and citations | Proposed facts awaiting verification |
| Highest-priority open finding and review count | Full review queue and competing evidence | Photo interpretation after an explicit submission |
| Microphone on/off, pause, capture failures | Captured transcript and processing trace | Confirmed-fact relay after authorization |
| Vehicle-server disconnection warning | Receiving-system delivery details | Queued packets, distinct from clinician acknowledgment |

Do not display a green “all good” state merely because nothing was captured. Missing values remain dashes; an unconfirmed new value does not become a large authoritative number. No simulated ECG waveforms, invented monitoring data, or decorative clinical animations.

The implemented default is an ambulance workspace with no administrative sidebar. Four readings keep stable positions. Review, Patient, Trends and Handoff open in place. Microphone controls and the priority strip remain available on the tablet layout. On narrow phones, the dock joins document flow so it does not obscure content. The older detailed view and guided presentation remain accessible through Settings.

## Touch, drag, zoom and information buttons

- Capture primary actions target at least 64 CSS pixels; secondary controls and the phase switch use at least 48-pixel-high controls. These are prototype choices, not a claim of glove usability.
- No drag-to-confirm, swipe-to-dismiss, drag-to-send, or automatic rearrangement of patient data. Accidental movement must not change a clinical fact.
- Photo drag-and-drop is available as a convenience with the same file chooser as a non-drag alternative. [WCAG dragging guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html) requires a single-pointer alternative when dragging is not essential.
- Arrange cards explicitly unlocks the two supporting modules, Capture & evidence and Receiving team. Pointer handles support mouse/touch dragging; Move earlier/later buttons provide keyboard and single-tap alternatives. Save locks and persists only card order; Cancel discards changes; Reset previews the default. Patient context, warnings, reading group and recording controls cannot be dragged. No automatic reordering or drag-to-confirm/send is permitted. Configure before care, not during a critical action.
- Expand a single reading to show its larger value and recent confirmed readings with timestamps/source labels. Opening transcript, visual evidence or handoff reveals that component's detail, not a magnified page. Global Large view is removed. Settings offers 100/125/150% text; browser zoom/pinch remains available. Photo preview retains 1×–3× zoom without changing the source image or extracted value. The [WCAG resize guidance](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html) informs the intended 200% acceptance check.
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

The source types are monitor, medication label, form and scene. This device's preview is live but inference runs only on the submitted still. This device's camera turns off when details close, the tab hides, or the connection fails. A submitted photo can continue processing while another panel is open; its progress/result is available from the visual-evidence card. New-patient changes cannot redirect that result to the next patient. The separate connected-camera workflow is described in `AGENTIC_CAPTURE.md`; it can continue when this local viewfinder is closed, and its state and Stop auto capture control remain in the dock.

Medication packaging does not prove administration, and a monitor photograph is not a live feed. Retain original evidence; never silently replace a device reading with OCR. S9 adds explicit region selection and bounded automatic still capture with patient association and capture gates; its real-model and physical-camera acceptance remain pending. No camera pathway may silently infer administration, identity, diagnosis, or scene facts that are not visible.

## What runs quietly, what interrupts

Extraction, trace updates and previously authorized relay can run without stealing keyboard focus or opening new panels. The attention strip remains stable while its text/count update. High-priority findings use existing deterministic rules and an assertive accessibility announcement; capture progress uses lower-emphasis status. No new audible alarms are introduced by this change. Opening the complete queue never means acknowledging a finding; confirmation and seen actions remain explicit.

The system must distinguish microphone active, clip processing, extraction finished, human verified, queued for sending, receiving server acknowledged, and receiving clinician acknowledged. Herald currently implements the first six—not the last. Connection to the vehicle server is separate from the hospital link.

## Validation and remaining product gates

Automated checks cover permission races, repeated clips, bounded backlog, stop/error handling, stale capture IDs, delayed cross-patient extraction, camera cleanup, unverified-value suppression, replay write protection, and WAV encoding. Layout checks additionally cover stored-order validation, explicit editing, save/cancel/reset, pointer cancellation/drop, individual expansion, focus restoration, disconnected camera wording and hidden backend IDs. These establish software behavior under test doubles, not microphone quality, physical reach, clinical safety, or model accuracy.

### Component review follow-up

The default view separates patient context and documented readings from supporting capture/handoff work. Backend incident fragments are removed from patient-facing headers; crew labels and start times preserve orientation. Actual patient identifiers remain clinical data in Patient and handoff details. Technical extraction metadata moves into Processing details while errors, unverified facts and evidence remain visible. Camera state distinguishes the connected automatic source from this device's viewfinder; a direct Stop auto capture stays available whenever automatic capture is enabled. Disconnection qualifies camera state as last known. Stopping is a server request and cannot be claimed successful while disconnected.

Two independent source-level reviews rated the initial layout 5/10 and the revised structure 7–7.5/10. These are subjective design critiques, not measured usability scores; their feedback drove focus restoration, direct automatic-capture stopping, stale-state wording and larger provenance text. Validation details for this iteration are in `WORKSPACE_POLISH.md`.

Verification in this clone: 117 backend tests and 44 frontend tests pass; the production build and light/dark theme-token contrast checks pass. Port 8101 serves the rebuilt bundle and AudioWorklet asset. Browser screenshots could not run because the browser distribution download timed out. Hardware speech/camera rehearsal remains required.

Before any real patient use, run a formative study with practicing paramedics using synthetic patients in a stationary ambulance: restrained reach, dominant/non-dominant hand, gloves, daylight/night, interruptions and recorded noise. Then use a controlled simulation for motion—not an experimental UI during active care. Measure mistaken patient attribution, missed warnings, accidental confirmations, time to find provenance, recovery from silence/disconnection, and task completion without explanation. Agree acceptance thresholds with clinical governance before collecting results. Test at 1024×768, tablet landscape/portrait, 390-pixel phones and 200% browser zoom.

Highest-priority backend gaps remain durable incident storage and recovery; event-level medication/procedure documentation; verified clinician identity/access/audit/retention controls; human receiving-team acknowledgment; and CAD/ePCR integration. A modern screen alone does not close these gaps.
