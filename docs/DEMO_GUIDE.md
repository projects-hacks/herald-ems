# Herald presentation guide

You do not need to explain the medical scores. The demo is one simple story:

> Herald listens while the medic works, builds a live patient picture locally, asks a human when information is
> uncertain, and sends only confirmed essentials to the ER.

## Open the rehearsal

Your clone is served on **8101**, not the shared demo's 8100. Open `http://localhost:8101/?mode=medic` through port forwarding for the ambulance workspace. Use Settings → Guided demo for the explanatory presentation. Only use synthetic patient information.

For a live-device rehearsal: tap Start listening once, speak a short patient observation, wait for the approximately eight-second clip plus local processing, then open Review. Ambient speech is unverified even if you spoke it. Tap Pause listening before leaving. This is continuous capture with short-clip transcription, not word-by-word streaming.

For vision: Camera → Open camera or Choose photo → Freeze image → inspect using zoom → Read this image → Review. Closing details stops the preview; a submitted image can finish reading in the background. Neither the microphone nor camera activates merely by opening the workspace. Both live device APIs require localhost/HTTPS. Visual and real-device rehearsal remain necessary before the presentation.

Use the forwarded Herald URL and add:

```text
/?fixture=stroke_demo&speed=2&at=1&present=1
```

The replay starts paused. The top-right controls are Play/Pause, Next moment and Restart. `Shift+P` switches between
the guided presentation and the real clinical screen.

## 90-second talk track

### 1. The problem — 10 seconds

Say:

> In an ambulance, important details are spoken once, scattered across people and devices, and the ER often receives
> an incomplete handoff. Herald turns that stream into a live, verified patient picture.

Press **Play**.

### 2. Listen and structure — 20 seconds

As the first sentences appear, say:

> The medic speaks normally. Herald runs locally in the ambulance and extracts the patient facts in seconds. The
> medic does not fill out another form, and no cloud AI is involved.

Point to **What Herald just heard** and **Patient picture**. Do not explain every field.

### 3. Close the pre-alert gaps — 15 seconds

As the green pre-alert segments fill, say:

> Herald knows what the hospital needs before arrival. The checklist closes as information is captured, while missing
> or uncertain items remain visible instead of being guessed.

Point to **Hospital pre-alert**.

### 4. Human-in-the-loop moment — 25 seconds

When the daughter says, “Mom is allergic to aspirin,” press **Pause**. Say:

> Here is the key safety moment. The husband said there were no allergies; the daughter says aspirin. Herald catches
> the conflict, keeps the new answer inside the ambulance, and asks the medic to choose. The AI never decides.

Point to **Human stays in control**. This is the judge beat; let it remain visible for a few seconds.

### 5. Weak-link handoff and privacy — 15 seconds

Say:

> The ER receives a tiny prioritized update. Confirmed fields are sent, uncertain facts are held, and raw audio and
> photos stay on the vehicle. If the link drops, updates queue and reconcile when it returns.

Point to **What the ER receives** and **Cloud AI calls: 0**.

### 6. Close — 5 seconds

Say:

> Herald gives the medic a second set of ears and gives the ER a cleaner head start—without replacing clinical
> judgment and without sending patient data to cloud AI.

## If a judge asks for technical detail

Select **Clinical view** or press `Shift+P`. Use only these points:

- **Scores are deterministic code; the model only extracts facts.** For this Santa Clara County stroke case the routing scale is **G.F.A.S.T. 4 of 4 → 700-A13 routing** (Protocol 700-A13: 4 of 4 routes to a Comprehensive Stroke Center unless the center is more than 45 minutes away). NEWS2 and RACE are computed and shown beside it as supporting context — RACE is not the county's routing rule, so lead with G.F.A.S.T.
- **Nothing uncertain leaves the ambulance until a human confirms it.** Model-only facts are held below the confidence bar and wait for a medic's tap.
- **Everything runs locally; the screen reports zero cloud AI calls.** Speech is Whisper (large-v3-turbo), fact extraction is the fine-tuned local model served as `ems-e-v2-fp8`, and photo reading is the local vision model served as `qwen3vl-fp8`.

### The agent loop (what actually runs)

If asked "is this just a chatbot / does it call some cloud tool?", describe the real loop — do not invent tool calls:

1. **Listen.** Continuous short-clip capture on the vehicle; Whisper transcribes each clip locally.
2. **Structure.** The local extractor turns speech into structured facts with per-fact confidence and provenance (who said it, linked to the audio).
3. **Watch (agentic capture, merged as S9).** When the camera is on, Herald sends at most one frame per second and reads on a budget (about one vision read every ten seconds, a single request in flight, speech gets priority). The status shows **Herald sees: off / watching / reading**.
4. **Hold for a human.** Every camera reading and every low-confidence fact is proposed, never auto-applied; a matching label never establishes dose, route, or patient. No treatment advice is given.
5. **Relay.** Only confirmed essentials are sent to the ER over the weak-link relay; raw audio and photos stay on the vehicle.

Press `Shift+P` again to return to the guided story.

## Recovery

- Lost your place: press **Restart**, then **Play**.
- Moving too quickly: press **Pause**; the screen remains valid at every moment.
- Live model or microphone problem: use this recorded fixture and state plainly that the screen is in recorded-demo mode.
