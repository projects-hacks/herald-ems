# Medic workspace redesign

Implemented in the `tushar-fs/herald-ems` checkout, 25 September 2026.

Herald's medic experience centers on a single encounter: capture observations, verify the patient picture, inspect changes, and prepare the receiving team. The overview makes the latest documented values and unfinished reviews visible. Secondary work has a consistent destination, and capture remains available while the medic moves between screens.

## Camera and page correction — 2026-09-25

- Removed the generic framed heading and Close details control from top-level medic destinations. Existing page content supplies its heading; Camera owns a single surface containing its title, patient context, tabs, and controls.
- Camera opens with Take a photo. Connected camera is a separate accessible tab within the same component, with the same button sizing and spacing. Opening the page or switching tabs never starts a device.
- Open camera and Choose photo live inside the compact initial state. Photo selection remains a file-picker alternative. A frozen photo survives workspace navigation; live preview stops when its tab or page is hidden.
- Empty photo extraction preserves the image and offers recovery. Successful extraction exposes Review readings. Permission denial explains the available recovery actions. Existing verification and patient-binding rules remain in place.
- Connected-camera setup uses `/classic/capture.html`, which the existing development proxy supports. The separate setup page still needs to remain visible on its camera device. Setup and capture mutations are unavailable in recorded replay.
- No-snapshot care destinations explain that patient data is unavailable. The review banner no longer claims zero items before receiving data; absent relay configuration is shown as unknown.
- Task pages use compact patient context, and the camera footer removes its redundant Camera/Type a note/Overview actions. Capture actions are at least 48 px high. Sidebar navigation and the overview breadcrumb provide page navigation.
- Verification: 108 frontend tests across 17 files; TypeScript and production build pass; token contrast checks pass. The existing bundle-size advisory remains. Isolated Chromium checks repeated three times at 1440 × 900, 1024 × 768, and 390 × 844 showed both photo-start actions above the dock, no horizontal overflow, and no page errors. Dark mode and tablet/phone 150% text also passed the checked states. Browser checks used intercepted API responses and simulated permission denial, not physical cameras.

The broader audit remains tracked in [MEDIC_UX_AUDIT.md](MEDIC_UX_AUDIT.md). This correction does not claim completion of note-draft persistence, operational phase events, legacy camera ownership, or the replay handoff work.

## Workflow

| Destination | Medic task | Implemented behavior |
|---|---|---|
| Overview | Understand the current patient | Identity and dispatch, call clock, important recorded history, review count, four documented vital cards, capture summary, receiving-team state and the active pre-alert checklist. |
| Review queue | Resolve uncertain information | Existing confirm/reject controls, contradictions, held findings, missing information and evidence. |
| Patient record | Inspect and correct the patient picture | Grouped facts with provenance, timestamps and the existing correction workflow. |
| Vitals & trends | Understand change over time | Confirmed reading history, published scores, inputs, missing values and source detail. |
| Capture timeline | Review what was heard or seen | Existing transcript/evidence processing with direct review and typed or bounded voice capture. |
| ED handoff | Prepare and share the patient story | Existing read-aloud report, format selection, confirmed-fact export, authorization and delivery status. |
| Protocol library | Consult local county documents | Search the existing library; show original passages, document/section/page/effective date, uncertainty and review flags, and links to the original page image. |

Patient management, display preferences, guided demonstration and new-incident controls remain available. Scene, transit and handoff are **screen-local phase controls**, not dispatch or transport lifecycle events. The existing backend remains authoritative.

## Visual system

- React + TypeScript + the established shadcn/Radix primitives, styled with shared CSS tokens. Lucide supplies consistent line icons. No second component framework was added.
- Light canvas, white bordered surfaces, dark slate text and teal interaction accents; a corresponding dark theme for lower-glare use. Existing saved theme preferences are honored.
- Inter for text and tabular numbers; clear patient and reading hierarchy, restrained borders, consistent rounded corners and shallow elevation.
- Alert colors retain their existing meanings and text labels. Category glyphs are not severity indicators. Readiness distinguishes captured, pending verification and missing items using words and different icons/patterns.
- Navigation becomes a compact rail on smaller tablets and a labeled horizontal strip on phones. The capture dock stays reachable while scrolling; enlarged text and short viewports use normal flow to preserve room for content.
- Camera task actions are at least 48 px high. Focus indicators, returning to the originating overview card, reduced-motion preferences, replay restrictions and device cleanup remain intact.
- Fonts are bundled locally. No external image or font request is needed for the design.

## Data and interaction boundaries

The redesign builds on the current capture, review and handoff implementation. It does not add patient data, clinical thresholds, recommended treatments, administration doses, fabricated monitor waveforms, human acknowledgment or a durable offline record. Vital sparklines use actual numeric confirmed history; unverified values remain hidden from the overview numbers.

Readiness comes from the snapshot. A completed pre-alert checklist is labeled **Captured**, not a claim that a clinician has received or accepted the handoff. Protocol results preserve the county text and its citation. An unanswerable result, uncertain text extraction or a document awaiting review stays visible. Pending protocol responses are discarded when the county or connection mode changes. Replay mode does not search the live service.

No backend API or snapshot shape changed. Search uses `GET /api/protocols/search?q=…&k=5`; original-page links use `GET /api/protocols/{doc}/page/{page}`.

## Original redesign verification

- Frontend: 102 tests passed across 17 files, including navigation, server-driven readiness, unverified-history treatment, protocol citations, unavailable-library errors, replay restrictions and discarding old-county responses.
- Backend regression suite: 465 passed, one skipped. No backend source changed.
- TypeScript and Vite production build pass. The existing bundle-size advisory remains.
- Theme contrast check covers the existing text/control pairs in both themes; all pass after adjusting the dark neurological-category foreground.
- Headless Chromium: seven care destinations at 1366 × 900, 1024 × 768 and 390 × 844; no uncaught page errors or horizontal overflow in those checks. 150% display scaling also checked. Screenshots reviewed for light/dark and phone layouts.
- These are software checks using recorded scenarios and mocked API responses. Physical microphone/camera, real-model latency, in-vehicle usability and clinical validation remain separate acceptance work.

## Preview

From `ui/`, run `npm run dev -- --host 127.0.0.1 --port 5184` with Node 22.12 or newer. The local review server uses that port. A self-contained recorded example is `http://localhost:5184/?fixture=stroke_demo&at=36&theme=light`; `theme=dark` opens the night palette. Replay actions stay disabled and the scenario is explicitly labeled. Live mode uses the existing `HERALD_API` proxy, defaulting to port 8101.
