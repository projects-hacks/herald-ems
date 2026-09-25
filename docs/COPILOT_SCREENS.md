# Herald copilot screens — design spec (2026-09-25, team lead direction)

Herald is an AI copilot for EMS, not a monitor and not an information dump. The medic's screen shows two
things: **what Herald needs from the medic** (decisions, one tap each) and **what Herald is doing on its own**
(clinical actions it took: heard, read, checked, sent). Everything else is one tap away, never ambient.

Test for every element: *is this an action for the medic, or a clinical outcome of something Herald did?*
If it is a status description, a capability explanation, a privacy disclaimer or a count, it does not belong
on the default screen. System status appears ONLY when something is broken, as one red line with a fix action.

## 1. Medic screen (the only default screen) — top to bottom

### 1a. Patient line (one line, sticky)
`68 M · Stroke alert · ETA 12 min → Regional CSC` — built from confirmed facts (summary, transport.eta_min,
transport.destination). Unknowns are simply omitted (no "Destination not confirmed" text). Right side: ONE
presence pill that is the whole system status: `● Listening · watching monitor` (quiet, small) when healthy;
it turns into a red pill with the fix when anything is broken ("Microphone stopped — Restart", "Extraction
model down — speech not becoming facts", "Offline — vehicle server disconnected"). Replay: `Demo replay` pill.
Remove: breadcrumb "Care workspace > Overview", phase buttons (On scene / In transit / Handoff), theme toggle
(move to Settings), separate CompactStatus/ConnectBand chatter when healthy.

### 1b. "Needs you" — the hero (left/main column)
A stack of decision cards the agent created, highest priority first, each ONE decision with at most two
buttons, written in clinical words. A card disappears when resolved (and appears as a line in 1c). Card types
(map from existing alerts/attention selectors, facts, capture verify results):
- **Confirm a reading** (camera/monitor): "Monitor 14:22 — HR 112 · BP 168/94 · SpO₂ 93 · RR 18"
  [Confirm reading] [Not right]. Confirm the whole reading in one tap (all facts from that frame/photo). Frame
  thumbnail on demand (tap the time), never inline by default.
- **Confirm what was heard**: batch per utterance: "Heard (daughter): aspirin allergy" [Confirm] [Reject].
- **Conflict**: "Aspirin 324 mg recorded as given — daughter reported aspirin allergy" [Review both] (opens
  the existing contradiction card with both sources + ▶ audio).
- **Label check**: "Bottle reads Warfarin 5 mg — you said Eliquis" [Use label] [Keep spoken].
- **Change**: "SBP 140 → 168 over 14 min" (+ "unconfirmed reading" tag and [Confirm reading] if it rests on one).
- **Missing for the ED** (gap-first checklists): "Stroke pre-alert still missing: last known well, glucose"
  [Record] (focuses typing/mic). Information, never advice.
- **Protocol match** (score + county rule, informational): "G.F.A.S.T. 4/4 — Policy 700-A13 §3.2: Comprehensive
  Stroke Center" [Open protocol].
Code status, allergies, meds: always individual cards, never batched.
Empty state: one line — "Nothing needs you right now." No explanatory paragraphs.

### 1c. "Herald is doing" — agent activity (right column; below on portrait)
Newest first, max 6 lines, past tense, time-stamped, clinical outcomes only:
`14:22 Read the monitor — HR 112, BP 168/94` · `14:21 Heard daughter: "she's allergic to aspirin"` ·
`14:20 Sent stroke pre-alert to Regional CSC — received 14:20` · `14:19 Checked the pill bottle label` ·
`14:18 Computed G.F.A.S.T. 4/4`. Build from snapshot data that already exists (transcripts, fact provenance
role/photo/monitor, relay packet log + acks, score changes, capture verify results). NOT allowed here: frame
counts, gate/reject reasons, queue depth, confidence numbers, model names. "Show all" opens the full record.
While the model is working on the latest clip: one quiet line "Listening… (processing last 8 s)" at the top.

### 1d. Movement strip (only when something moved)
One compact row per vital that CHANGED across the journey: `SBP ↑ 140 → 152 → 168 · 14 min` with a tiny
sparkline. If nothing changed: a single line "No change across N readings". No four big vital tiles on the
default screen (the ambulance monitor shows current values). Tap → Trends page.

### 1e. ED card (small)
"Regional CSC has: stroke alert, G.F.A.S.T. 4, LKW 13:04, warfarin · last update 14:20 ✓ received" and, if
any, "2 facts wait for your confirmation before they can be sent" (tap → Needs you). Button: Handoff report.

### 1f. Dock (bottom, sticky) — controls only, no prose
Three controls: the mic toggle is the big primary button and carries its own state ("Listening" with a live
level ring / "Start listening"); Camera; Type (merges "Manual entry" + "Type a note" — one text box that
becomes facts; keep the structured manual-entry form reachable from inside it). REMOVE the status paragraphs
("Microphone off", "Connected camera: status unavailable", the privacy line). Errors surface only via the red
presence pill (1a). The authorization/privacy text moves to Settings. If the mic needs HTTPS/localhost, the
pill says "Microphone blocked by browser — open via localhost" once, not a paragraph.

## 2. Secondary pages (opened from nav, never on the default screen)
Nav collapses to: Now (default) · Record (all facts, grouped, provenance on tap) · Trends · Handoff ·
Protocols · Camera · Settings. Patients appears only when >1 patient (mass-casualty strip at the top).
- **Record**: facts grouped by clinical section (history, meds, allergies, exam, scores); each row: value,
  status chip (confirmed/unconfirmed/held), and provenance on tap (source, time, ▶ audio / frame).
- **Trends**: current trend view (StatTiles, VitalReadings, charts) lives here.
- **Handoff**: read-aloud MIST/SBAR + what was sent/received per packet + reconciliation counter.
- **Camera**: viewfinder, monitor-watch start/stop and ROI, take a photo. Explanatory copy trimmed to one line.
- **Settings**: text size, theme, new incident, guided demo, privacy/authorization and "what runs in the
  background" copy, prototype disclaimer.

## 3. ED screen (ed_receiver/web) — the receiving clinician's wall display
Top: `INCOMING · Stroke alert · ETA 12 min` with live countdown, the one thing to prepare for. Critical band
(existing config/ed_display.yaml keys, 48 px). "Changed since last update" highlighted, newest first. Then
the rest of the confirmed record. No transport/system chatter; a single line when the link is stale.

## 4. Unchanged rules
Text ≥13 px, critical 20 px; targets 48 px / primary 64 px; priority = colour + icon + word; confirmed-only
to the ED; unconfirmed readings may alert the medic, labelled; Herald never recommends treatment; offline /
stale / model-down stay honest (now via the presence pill + one line).
