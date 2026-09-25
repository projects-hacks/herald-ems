# Medic workspace UX audit

Date: 2026-09-25. Checkout: `tushar-fs/herald-ems`.

Status: original audit with a subsequent camera/page correction. See the implementation status below; remaining findings are still open.

The current workspace has a consistent visual shell, but its first-use, disconnected, capture, and recovery paths are incomplete. The reported blank trends panel and confusing camera setup are symptoms of those missing states. This audit follows the medic journey rather than evaluating only a populated dashboard.

## Implementation status after camera/page correction

See [MEDIC_WORKSPACE_REDESIGN.md](MEDIC_WORKSPACE_REDESIGN.md) for the shipped composition and verification scope.

- Addressed in the medic workspace: UX-01 unknown review/relay state; UX-02 null-snapshot destinations; UX-04 setup route; UX-07 competing camera panels; UX-08 starting action visibility at the audited viewport sizes.
- Partially addressed: UX-09 now retains zero-result images, offers a Review action, and explains denied permission; HTTP/uncertain-completion recovery still needs work. UX-10 distinguishes unavailable connected-camera state and local preview. UX-12 removes the generic frame/close CTA and duplicated wrapper headings; URL/history behavior is unchanged. UX-15 increases camera-status text; the wider typography/field-readability audit is open.
- Still open: UX-03 note drafts, UX-05 legacy camera ownership, UX-06 direct note entry, UX-11 phase semantics, UX-13 case-action discoverability, UX-14 replay handoff, and UX-16 connection recovery.
- Follow-up validation: 108 frontend tests; TypeScript/build; theme token contrast; isolated responsive camera and failure-state checks, three repetitions each. No backend or clinical-rule changes.

The findings below retain the original observations so the remaining work and the reason for each correction stay reviewable.

## Evidence and limits

- Inspected the React medic workspace, its legacy camera destination, connection handling, and existing tests.
- Reproduced the browser findings below in Chromium against the local Vite preview. Used the recorded `stroke_demo` fixture at message 36, then controlled client state for disconnected and live simulations. All API calls during interactive checks were intercepted; no patient records or shared services were changed.
- Repeated the final browser checks three times. Each reported outcome occurred in all three runs. The layout coordinates in the table below were identical across those runs.
- Simulated camera permission denial, an empty photo extraction response, and legacy-page visibility changes. These establish client behavior, not physical camera reliability, operating-system permission UX, or extraction accuracy.
- Inspected desktop, tablet, and phone viewport layouts; these were browser viewport checks, not physical-device field trials.
- An initial browser harness selector matched both a hidden overview summary and the visible photo result. The selector was scoped to the camera component before the three completed repetitions; this was a harness issue.
- No application code changed during this audit. The earlier passing suite does not establish that these workflows are usable. In particular, `cabin.test.tsx` checks that the note textarea exists, not that the medic can see it after clicking “Type a note.”

Evidence labels: **Browser** means reproduced in the isolated checks; **Code** means confirmed by source inspection; **Design** means a recommended interaction improvement. P1 means misleading state, loss of work, or a blocked primary task. P2 means significant friction, unclear feedback, or poor discoverability.

## Prioritized findings

### UX-01 — P1: Unknown patient state is presented as a clear review queue

**Browser + Code.** Before any snapshot arrives, the workspace displays a check icon, “No open review items,” and “0 to review.” It also says “showing last state” and “ED not configured,” although there is no previous state or known relay configuration. The disclaimer about missing information does not repair those affirmative claims.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 59 and 95–99; [CompactStatus](../ui/src/components/CompactStatus.tsx), lines 8–11. Reproduced with `snapshot = null`, `source = live`, `conn = closed`.

**Correction:** Distinguish connecting, unavailable, current, and stale data. Use “Review unavailable — waiting for patient data” with a neutral icon before the first snapshot. Show a last-update message only when cached state exists. ED configuration is unknown until received.

**Acceptance:** A failed initial connection cannot produce a checkmark, a definitive zero review count, or a claim about ED configuration. An actual empty queue remains a separate state.

### UX-02 — P1: Several destinations become empty framed panels

**Browser + Code.** Vitals & trends, Patient record, ED handoff, and Manage patients contain only their heading and “Close details” when no snapshot exists. Review queue adds a heading and a dash, without explaining availability. This reproduces the reported trends screenshot and extends beyond that screen.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 103–110; [TrendsPage](../ui/src/pages/TrendsPage.tsx), line 57; [PatientPage](../ui/src/pages/PatientPage.tsx), line 50; [HandoffPage](../ui/src/pages/HandoffPage.tsx), line 89; [PatientRoster](../ui/src/components/PatientRoster.tsx), line 17.

**Correction:** Render explicit loading, no-data, unavailable, and error content at the destination level. Give the medic an available next action. A chart container should appear only when there is content to plot.

**Acceptance:** Every destination has meaningful content with a null snapshot. Empty trends show an explanation and an appropriate next step, never just a title, divider, and close control.

### UX-03 — P1: Navigating away silently discards an unsent note

**Browser + Code.** Enter a note, select Patient record, return to Type a note, and reopen the editor: the draft is empty. Switching panels unmounts `CaptureBar`, whose text is component-local state.

Evidence: [CaptureBar](../ui/src/features/capture/CaptureBar.tsx), lines 13 and 55–60; [CabinApp](../ui/src/features/cabin/CabinApp.tsx), line 109. Reproduced three times without submitting anything.

**Correction:** Preserve drafts in patient-scoped session state across workspace navigation. Show “Draft — not submitted.” Define explicit discard and patient-change behavior; never carry a draft into another patient's submission.

**Acceptance:** Navigating away and back preserves the draft and source selection. A patient switch never silently reassigns it. Submission success and explicit discard clear only the intended draft. Do not imply durable offline storage unless implemented.

### UX-04 — P1: Camera setup link returns to the main app in development

**Browser + Code.** “Open camera & set region” links to `/capture.html`. In the Vite preview that URL returns HTTP 200 with the main React entry point, not camera setup. The proxy covers `/classic`, `/api`, and `/ws`, but not `/capture.html`. This is an environment-specific routing bug; the backend has a separate `/capture.html` route.

Evidence: [CaptureControl](../ui/src/features/capture/CaptureControl.tsx), line 39; [Vite configuration](../ui/vite.config.ts), lines 24–27; [backend route](../herald/api/app.py), lines 63–65. All three browser requests returned the main app HTML with no `start-camera` control.

**Correction:** Use one route that resolves in development and in the backend-served build, preferably integrated camera setup. Remove inconsistent `/capture.html` versus `/classic/capture.html` navigation.

**Acceptance:** Following every photo/setup entry point reaches the intended capture experience in both serving modes.

### UX-05 — P1: An idle legacy camera tab can send a global stop command

**Browser + Code.** Hiding the legacy camera page invokes `stop()` unconditionally. Even a tab that never started a camera posts `{ "on": false }` to `/api/capture/auto`, without an incident ID. The backend accepts an omitted incident ID and changes the capture agent's auto state. This creates a path for an idle setup tab to interfere with capture controlled elsewhere.

Evidence: [continuous.js](../web/continuous.js), lines 19–22 and 126; [capture API](../herald/api/routes/agentic_capture.py), lines 20–26 and 57–64. In each isolated visibility-event test, an untouched page sent exactly that stop request. Interference with a second physical camera was not exercised.

**Correction:** Tie stop commands to the owning capture session/source and patient. Preserve the intentional local stop on hiding an active camera, with clear paused feedback. Do not send server mutations from a page that owns no active capture.

**Acceptance:** Hiding an idle setup tab emits no stop request. Hiding an active owner stops only its capture. Returning shows an explicit Resume action. A medic can understand that a separate camera tab must remain visible, or setup is integrated into the workspace.

### UX-06 — P2: “Type a note” does not expose or focus the editor

**Browser + Code.** The action opens the entire capture timeline, places the form below its entries, and leaves its `<details>` closed. Focus lands on the page heading. The user must discover another “Type a note or enter a monitor reading” expander.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 109 and 152; [CaptureBar](../ui/src/features/capture/CaptureBar.tsx), line 55. The textarea was invisible after the first action in all three checks.

**Correction:** Separate “write a note” intent from “browse captures.” Open a visible composer directly, focus its textarea, and keep the active patient in view. The timeline can remain available underneath or alongside it.

**Acceptance:** One click exposes an enabled editor when connected, or explains why submission is unavailable. No second expander or scrolling through old notes is required.

### UX-07 — P2: Camera setup exposes two competing workflows at once

**Code + Design.** “Connected camera · automatic capture” and “This device · freeze and read a photo” each have their own mode selector and action model. A third experience opens in a legacy tab. “Show Herald,” “Auto choice,” “set region,” “Freeze image,” and “Read this image” do not establish a clear starting point or explain which camera each controls.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 136–137; [CaptureControl](../ui/src/features/capture/CaptureControl.tsx), lines 27–40; [CameraCapture](../ui/src/features/cabin/CameraCapture.tsx), lines 85–109; [legacy page](../web/capture.html), lines 13–36.

**Correction:** Start with a task choice: “Capture a photo” or “Watch a monitor.” Show only the selected workflow. Identify its source explicitly. Default to a one-time photo; expose monitor-region setup only for monitor watching. Use action verbs such as “Open camera,” “Capture photo,” “Read photo,” and “Review readings.” Keep numeric region bounds in advanced settings.

**Acceptance:** The selected workflow has one source, one purpose selector, one primary action, and a visible next step. Opening the camera page never starts recording automatically.

### UX-08 — P1: Camera's primary action starts far below the visible workspace

**Browser + Design.** Global patient context, the full review banner, an otherwise empty “Capture visual evidence” card, and the connected-camera card precede the local camera. The camera-off placeholder occupies more space before its actual buttons. At 1440 × 900, Open camera starts around y=1245 while the dock starts at y=784. The phone dock occupies roughly one third of the screen.

| Viewport | Open camera top | Dock top | Dock height |
|---|---:|---:|---:|
| 1440 × 900 | 1244.69 px | 783.69 px | 116.31 px |
| 1024 × 768 | 1295.69 px | 580.69 px | 187.31 px |
| 390 × 844 | 1633.52 px | 557.77 px | 286.23 px |

These are screen coordinates immediately after opening Camera in the recorded-patient simulation, at default text size. They measure action discoverability, not horizontal overflow.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 84–104 and 136–155; [CameraCapture](../ui/src/features/cabin/CameraCapture.tsx), lines 93–106.

**Correction:** Place Open camera and Choose photo inside a compact initial state at the top of the task. Expand the viewfinder after opening. Collapse the large patient hero to a compact patient bar on task pages. On phone, give the task a compact action bar and move secondary actions into a menu while keeping recording state and stop available.

**Acceptance:** The starting capture action is visible on entering the task at the three audited sizes. Sticky controls do not cover the active field or focused control, including at larger text settings.

### UX-09 — P2: Photo results and permission errors give inadequate recovery

**Browser + Code.** A successful response with zero facts produces “0 proposed facts. Open Review to verify against the original image,” clears the preview, and provides no local Review action. Simulated permission denial displays only “Permission denied.” HTTP failures become a status-code message without using the response's reason.

Evidence: [CameraCapture](../ui/src/features/cabin/CameraCapture.tsx), lines 62, 79–82 and 108. Zero-result behavior and permission copy reproduced in all three runs.

**Correction:** Use separate states for no readable information, successful extraction, permission blocked, source disconnected, model unavailable, and uncertain completion. Preserve the image when retrying is useful. Offer Retake, Choose another photo, and an actual Review readings action where applicable. For uncertain completion, link to the capture entry before allowing a duplicate retry.

**Acceptance:** Zero facts never instruct the user to verify nonexistent results. A successful extraction links to its proposed facts. Permission denial explains how to recover or choose a file. An uncertain server result does not claim that nothing was saved.

### UX-10 — P2: Camera status describes different sources inconsistently

**Browser + Code.** With no `snapshot.capture`, the connected-camera card says “Herald sees: off,” while the dock says “Connected camera: status unavailable.” The dock reads only the server camera state; the local browser preview's active state is not included in `CameraStatus` passed to its parent.

Evidence: [CaptureControl](../ui/src/features/capture/CaptureControl.tsx), line 30; [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 64 and 144; [CameraCapture](../ui/src/features/cabin/CameraCapture.tsx), lines 5 and 22.

**Correction:** Use source-specific status: “This device: preview on,” “Monitor camera: disconnected,” and “Photo: processing.” Distinguish unknown from off. Place status beside the controls for that source.

**Acceptance:** The same source cannot be off and unknown simultaneously. The active preview, automatic capture, queued extraction, and disconnected source are distinguishable without opening Settings.

### UX-11 — P2: Phase controls look operational but only change local UI state

**Code + Design.** On scene / In transit / Handoff updates `ui.incidentPhase`; Handoff also opens its panel. It does not record a transport event or update the patient record. The “this screen only” explanation is in an accessibility label and Settings, not beside the visible controls.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 68–70 and 113.

**Correction:** Either make the controls clearly named workspace views or implement a real, confirmed workflow transition backed by the appropriate product/API contract. Do not visually imply recorded operational progress from a cosmetic selection.

**Acceptance:** A medic can tell whether the control changes their view or records an event. Navigation and the selected phase do not communicate contradictory workflow states.

### UX-12 — P2: Top-level destinations still behave like dismissible detail panels

**Code + Design.** Sidebar navigation opens a generic card with an X and Close details, with another Overview button in the dock. Breadcrumb, outer title, and inner page title repeat the same hierarchy. Camera and Settings inherit a panel pattern despite being full tasks; camera's outer panel contains no task content. Panel selection is local component state, without a corresponding navigation history update.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 33, 45–51, 67, 103–120 and 153; [WorkspaceNav](../ui/src/features/cabin/WorkspaceNav.tsx), navigation button handlers.

**Correction:** Treat sidebar destinations as pages with one heading. Reserve close icons for actual dialogs, drawers, or expanded details. Preserve page location in navigation state/URL where appropriate and define browser Back behavior.

**Acceptance:** Changing destination has one predictable navigation result; there is no empty framing card. Closing a drawer returns to its originating task without resetting unrelated work.

### UX-13 — P2: Starting and managing a case is poorly discoverable

**Code + Design.** The medic workspace's New incident action sits in Settings & display. Patients opens another “Patients · manage” expander before showing the add form. The initial patient hero says “Start capture or enter a patient fact” even when those actions are unavailable because the connection has failed.

Evidence: [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 87 and 117; [PatientRoster](../ui/src/components/PatientRoster.tsx), lines 20–25. The existing new-incident dialog correctly explains replacement of the roster; retain that confirmation.

**Correction:** Put case actions in the patient/case area, separate from display preferences. Provide a deliberate first-use state with connection readiness and the next available action. Distinguish adding a patient to the current incident from replacing the incident.

**Acceptance:** A first-time medic can find the correct action without searching Settings or expanding a second management section. Destructive incident replacement retains explicit confirmation.

### UX-14 — P2: The replay handoff path leads with an unavailable report

**Browser + Code.** The recorded demo's ED handoff opens with “This recording does not include a full handoff report.” An existing snapshot-based summary and text export are collapsed underneath. This interrupts a principal hackathon workflow despite usable recorded data being available.

Evidence: [HandoffReport](../ui/src/features/handoff/HandoffReport.tsx), line 34; [HandoffPage](../ui/src/pages/HandoffPage.tsx), lines 93–96. The unavailable message was visible and the fallback summary closed in all three checks.

**Correction:** Lead with the available snapshot summary, clearly labeled as the recorded scenario. Alternatively extend the fixture to include the structured report. Never fetch a live patient's report to fill a replay gap.

**Acceptance:** The handoff CTA in the demo immediately reveals a useful, truthful report or summary without another discovery step.

### UX-15 — P2: Critical supporting text is too small for the intended setting

**Browser + Design.** Camera status computes to 9.6 px at default scale. Other supporting labels use approximately .6–.68 rem. A token contrast check cannot establish that timestamps, processing status, and missing-information labels are readable during field use.

Evidence: [medic.css](../ui/src/features/cabin/medic.css), patient/status, readiness, and dock typography overrides. The computed camera-status size was 9.6 px in all three desktop runs.

**Correction:** Increase operational supporting text and reduce repeated content and decorative space to recover room. Use the established type scale consistently. Validate at the intended viewing distance and with the actual tablets, gloves, lighting, and larger-text settings.

**Acceptance:** Status remains legible and unclipped at default and 150% text. Physical-device readability is validated separately; no accessibility-conformance claim follows merely from passing the palette script.

### UX-16 — P2: Connection failure copy lacks an actionable recovery path

**Code + Design.** The banner asks “Is it running?” and prints `location.host`. With a Vite proxy, that identifies the UI host rather than necessarily identifying the unreachable backend. Auto retry is present, but the medic sees no connection details/recovery action and is simultaneously invited to use disabled capture controls.

Evidence: [GlobalStates](../ui/src/components/GlobalStates.tsx), lines 13–24; [Vite configuration](../ui/vite.config.ts), line 9; [CabinApp](../ui/src/features/cabin/CabinApp.tsx), lines 87 and 148–152.

**Correction:** State the impact in plain language: patient data and submission are unavailable while reconnecting. Provide connection details/recheck appropriate to the deployment, and put technical endpoints in those details. Offer a clearly labeled recorded demo where relevant to the hackathon, without disguising it as a live encounter.

**Acceptance:** Initial failure and stale cached data have different messages. Every unavailable primary action has a visible reason and a next step the medic can actually take.

## Proposed interaction shape

### Vitals and trends

| State | Content and next action |
|---|---|
| Connecting, no snapshot | Compact loading state identifying what is being loaded. |
| Connection failed, no snapshot | Patient data unavailable; connection recovery/details. No blank chart or clear-review indicator. |
| Connected, no readings | “No readings recorded”; Add reading or Capture monitor, subject to actual availability. |
| Unverified readings only | Explain that verification is required; link directly to those readings. |
| One confirmed reading | Show value, units, source, and timestamp; explain that a second confirmed reading is needed for a trend. |
| Multiple confirmed readings | Render the real history with timestamps and units. |
| Stale snapshot | Keep the last received values visibly timestamped; explain that they are not current and changes are paused. |

### Camera

1. Choose **Capture a photo** or **Watch a monitor**. The first screen contains the available starting actions.
2. Identify the camera source. Offer **Open camera** and **Choose photo** for a one-time capture; provide an actual device/source selector where supported.
3. Show the preview with **Capture photo**. Monitor watching adds a visual region-selection step and an explicit start action. No background start on navigation.
4. Inspect the captured image with **Retake** and **Read photo** beside it.
5. Show a source-specific processing state, then **Review N readings** or a useful no-result recovery state.
6. Review proposed values against their evidence; preserve the existing confirmation requirements before scores or sharing use them.

The source choice and capture mode should be progressively disclosed rather than displayed as two full competing workflows. Pause/resume and ownership must be explicit when tab visibility or patient context changes.

## Fix order and verification

1. Correct state truth and blank destinations: UX-01, UX-02, UX-16.
2. Protect drafts and deliver direct note entry: UX-03, UX-06.
3. Correct camera routing/ownership, then consolidate its flow and recovery: UX-04, UX-05, UX-07–UX-10.
4. Simplify page hierarchy, case actions, phase semantics, and typography: UX-11–UX-13, UX-15.
5. Finish the recorded handoff journey: UX-14.

Add meaningful workflow checks alongside the fixes: startup without data; delayed connection; empty/one/many confirmed readings; stale snapshots; visible and focused note entry; draft retention across navigation; patient-scoped drafts; camera setup under both serving modes; idle-tab ownership; blocked permissions; zero and multiple photo facts; uncertain completion; keyboard focus; phone/tablet action visibility; and replay handoff. Exercise light/dark and enlarged text on the affected screens.

Retain the existing protections: explicit device activation, stop on hidden/unmounted local capture, patient association checks, proposed-photo verification, confirmed-only sharing, and clear separation of technical delivery from a clinician reading the report.
