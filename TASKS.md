# Remaining work

Keep this file to unresolved product work and acceptance checks. Completed implementation history is in git. Submission, presentation and pitch work live outside this repository.

## Product acceptance

- [ ] Validate the entire microphone/camera → proposed fact → review → patient change → ED report path with the approved serving stack. Fake-adapter tests do not establish extraction accuracy or latency.
- [ ] Test mounted physical cameras against changing monitor readings, angles, glare and vibration. Measure missed/spurious observations and capture-to-review latency; test ROI, device unplugging, permissions and reconnects.
- [ ] Evaluate ambulance-noise speech, overlapping speakers, medication/procedure events and audio/vision contention. Record speaker attribution and review burden, not just fact accuracy. Use `eval/field/` and its consent/labeling protocol.
- [ ] Verify patient switches, incident end, recovery and evidence deletion with simultaneous capture devices and pending extraction. Check that no stale capture attaches to another patient.
- [ ] Run the receiving screen on a second machine over a constrained link. Check critical-first delivery, later full history, care-event timestamps, units, and delivery versus clinician receipt.
- [ ] Validate gloved interaction, screen readers, 150% text, reduced motion, long transcripts and three-meter ED readability on target hardware with representative users.
- [ ] Repeat the full uncontended 30-minute soak. Earlier contention runs did not pass latency acceptance; see `docs/RUNBOOK.md`.
- [ ] Rebuild from a clean clone/container, verify model/terminology asset availability and record actual cold-start behavior.

## Remaining interaction issues

- [ ] Preserve unsent typed notes across navigation, and make “Type a note” open/focus its editor.
- [ ] Distinguish uncertain HTTP submission outcomes from a definite rejection before offering retry; prevent duplicate capture submissions.
- [ ] Decide whether care-phase controls should persist per incident; they currently describe local UI state.
- [ ] Add browser Back/Forward behavior for care-page navigation and improve incident creation/discovery.
- [ ] Validate permission-error recovery and clear connection diagnostics on the deployed devices.

## Model and clinical content

- [ ] Finish the active model work and acceptance gates in `docs/TRAINING_PLAN.md`; preserve held-out data separation and report repeated-run spread.
- [ ] Re-run protocol reranking on all 59 questions and verify archived county documents against the in-force manual before updating clinical content.
- [ ] Complete real-speaker and real-photo evaluations, speaker diarization feasibility, and interpreter acceptance before claiming those capabilities.

Clinical source data, labeling rules, benchmark evidence and active training work remain in the repository. Do not delete them as completed planning material.
