# Ambulance workspace: component-focused refinement

2026-09-25 · Tushar's clone · `feat/workspace-polish`

## Delivered

- Patient context, priority review and documented readings lead; supporting work is grouped into Capture & evidence and Receiving team.
- No whole-page Large view. Each reading expands independently into its confirmed history, recorded times and source labels. Other desktop readings retain their columns. Transcript, evidence and read-aloud handoff have their own detail views.
- Arrange cards unlocks only the two supporting cards. Drag handles, Move earlier/later, Save, Cancel and Reset work without mutating clinical state. Only validated layout identifiers enter local storage. Layout changes never happen in response to new facts.
- Crew labels and call start replace backend incident fragments in headers and handoff fallback copy. Clinical patient identifiers remain available in patient details. Internal identifiers remain in API, provenance and export metadata for traceability.
- Patients management is a deliberate action; the multi-patient strip remains available when relevant. Technical transcript metadata moves under Processing details, while failures, evidence and mismatch review remain visible.
- Camera wording distinguishes connected automatic capture from this device's viewfinder, qualifies stale state, and never assumes a missing status means off. Stop auto capture remains accessible when enabled; a disconnected stop request cannot be presented as successful.
- Light/night styling, larger recorded-time metadata, keyboard focus recovery, and enlarged-text reflow. Enlarged accessibility text lets the status/capture bars join document flow so they do not cover the patient content.

## Verification

- Backend regression suite: 465 passed, one skipped; no model loads or GPU runs.
- Frontend regression suite: 95 passed across 16 files, including layout persistence, malformed preferences, drag cancellation/drop, non-drag ordering, keyboard focus, component expansion, missing/stale camera state and transcript mismatch navigation.
- TypeScript/production build passed. Existing bundle-size warning remains (approximately 525 kB minified main bundle).
- Existing light/dark token contrast checks passed; no severity-color changes.
- Firefox 156 headless: real pointer drag changed the supporting-card order; Save survived reload. Screenshots inspected in daylight/night themes, at 1440 px desktop and 1024×768 tablet. At standard tablet text size, all four reading cards fit above the capture dock.
- Responsive content inspected in a 390 px same-origin iframe because the desktop Firefox window cannot shrink below 500 px. No horizontal page overflow. This is a layout check, not a physical phone test.
- Individual expansion preserves the four desktop reading columns. The actual 150% text setting reflows without horizontal overflow or pinned-bar obstruction. A manual 200% root-font stress check initially exposed bar obstruction and motivated reflow; native 200% browser zoom still requires acceptance testing.
- Two independent source-level reviews rated the original design 5/10 and the revised structure 7–7.5/10. These are subjective critiques, not measured clinical usability. Their findings drove concrete changes; no field-validation claim is made.

## Preview and boundaries

The static preview is served from this clone on port 8101:

`http://localhost:8101/?fixture=stroke_demo&at=30&mode=medic&theme=light`

This uses a recorded synthetic scenario, not a live patient. Capture and server writes are disabled; the old fixture does not contain a full MIST/SBAR report. Physical touch/glove interaction, microphone/camera hardware, real-model acceptance and practicing-paramedic simulation remain outstanding. No shared demo instance, clinical rules, API contract or model serving configuration was changed.
