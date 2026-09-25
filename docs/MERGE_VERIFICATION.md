# Tushar branch integration — 2026-09-25

The owner requested merging the three published branches into main: ambulance UI (`f8aaa70`), agentic capture (`88ac480`), and UI review fixes (`6a35edd`). Integration starts from main `b0d264c`, including its patient roster and current model-only extraction. No other contributor's unmerged branch is included.

## Reconciled behavior

- Default medic view is the ambulance workspace. Guided demo and detailed application remain available. Patient selection, compact model/ED status, camera auto/Show Herald and evidence review are accessible in the ambulance workspace.
- Continuous ambient audio remains explicitly started, bounded and speaker-unverified. Push-to-talk and typed/monitor entry share one implementation across screens, retaining release-before-permission, timeout and patient-change safeguards. No recorder starts on mount.
- Current patient roster and relay maps take precedence over older single-patient assumptions. New incident replaces the roster; Add patient belongs to the existing incident.
- Camera listeners survive request-scoped capture. Patient switches disable automatic capture, clear ROI and pending work, and reject stale controls. Delayed extraction cannot enter the next patient's record.
- Medication mismatches use Keep as said/Edit in both review and Patient views. Neither generic confirmation nor generic correction bypasses an unresolved mismatch.
- Current MIST/SBAR API report remains the authoritative read-aloud view. The older snapshot summary/export remains available separately and includes confirmed medication/procedure events. Technical delivery is not human acknowledgment.
- Current contract vocabulary, all-event review, county alert wording, ED display fixes, tablet status, checklist switching and minimum touch targets are retained. Old rules-fallback copy and tests were updated to model-only extraction with injected fakes.

## Verification boundary

Combined checks passed: **465 backend tests, one skipped; 77 UI tests; TypeScript/production build; light/dark contrast checks; whitespace checks**. The build reports a non-blocking bundle-size warning (about 516 kB before gzip). These establish software integration behavior, not real-model performance or clinical validity.

Verification uses fake models and CPU-only tests/builds. No service restart, GPU work, neural-model load or fixture re-recording is part of this merge. Real-model acceptance still requires Rajeev's serving approval; physical microphone/camera, tablet and ED-distance testing remain open. U13 recording remains gated on model lock; U8 startup-default changes belong to Vineet's branch.

The original feature branches and named stash are preserved for audit/recovery. Main is updated only after combined regression checks pass; no history is force-pushed.
