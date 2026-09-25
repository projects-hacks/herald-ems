# Agentic capture

Camera capture is opt-in. The medic remains responsible for confirming every camera reading and resolving label mismatches. A matching ingredient label does **not** establish the dose, route, patient, or administration. The feature provides no treatment recommendation.

## Current verification boundary

Development uses fake speech/vision adapters, the real deterministic policy and RxNorm coding algorithm with a small test index, and synthetic equipment images. These tests establish software behavior, **not** model accuracy or clinical validity. No GPU or neural-model loads are needed. Real-model acceptance starts only after Rajeev explicitly confirms `herald-f` is serving, not merely when the expected time passes.

Shared-machine memory controls and launchers may live in the active deployment checkout while training work is in progress. Use that checkout’s memory policy and guarded launcher with its owner; do not substitute an unguarded start if they are absent here. Ordinary application startup can load models and must wait until the training reservation ends.

## CPU-only verification now

From this clone, using the existing Python environment:

```bash
/home/hp18/miniforge3/envs/zgx/bin/python -m pytest -q
/home/hp18/miniforge3/envs/zgx/bin/python -m pytest -q tests/test_capture_replay.py
cd ui
npm test
npm run build
```

The replay integration test exercises monitor changes, unconfirmed readings, a mismatching vial without adding home medications, manual capture while auto is off, and used-frame retention. Separate tests exercise the fake speech extractor, gates, rate/speech priority, matching/ambiguous codes, explicit edits, stale patient controls, and redaction failures.

## Camera workflow (approved application instance only)

1. Open the medic workspace and choose **Camera → Monitor watch**. Capture never starts on page load. The standalone `/capture.html` remains available.
2. Choose **Start monitor watch** and allow the camera. Aim at equipment and adjust its region with the percentage controls; the workspace initially uses the full frame. Apply changes explicitly. Return to another care page without stopping the feed. The standalone page also supports dragging a region.
3. The page sends at most one JPEG per second, at most 1280 px long side, with one unacknowledged frame. Only selected stills reach vision. The global automatic ceiling is one admission per ten seconds; monitor watch also has a 15-second minimum interval. One inference runs at a time, with speech admission priority.
4. NOW shows **Herald sees: off / watching / reading**, the automatic switch, the mode picker and **Show Herald**. Watching requires recent frames, not just an enabled switch. Trace cards expose the reason, proposed facts, and retained evidence.
5. Label mismatch cards offer **Keep as said** or **Edit**. Neither automatically changes a spoken drug. Editing preserves the other dose fields and retains the rejected original in history.
6. Stop capture, change patient, hide the camera tab or close its connection to stop the camera path. New patients require an explicit restart and a new region. An in-flight model call cannot be cancelled inside its worker, but obsolete results cannot attach facts or store images.

For the second-laptop setup, open `/monitor.html` on the equipment-display laptop and choose **Start changes** or **Next readings**. It displays clearly synthetic values from `/fixtures/monitor_journey.json`, writes no patient facts and needs no backend. Point the observing camera at it; extraction, review, trends and relay must occur through the normal pipeline. Current synthetic browser tests substitute a camera stream and server admission, so they do not establish real vision accuracy.

Continuous camera requires a secure browser context:

- On an observing laptop, forward the approved instance with `ssh -L 8101:127.0.0.1:8101 hp18@<nano-host>` and open `http://localhost:8101/capture.html`.
- For a phone, use an HTTPS instance with a certificate trusted by that phone. Provision the certificate/key outside the repository; add `--ssl-certfile /absolute/path/cert.pem --ssl-keyfile /absolute/path/key.pem` to the approved uvicorn launch. A self-signed certificate needs explicit device trust; a warning bypass is not reliable camera authorization. Do not expose this unauthenticated hackathon service to the public internet.
- The existing one-shot file/camera picker remains a fallback. It uses the legacy `/api/photo` path and its existing retention behavior, not the new in-memory stream. Keep patient faces out of those photos.

## Privacy and configuration

`HERALD_CAPTURE_SOURCE=off|browser|replay:<folder>`; `HERALD_CAPTURE_AUTO=0` by default. Local USB/V4L2 support is optional and not implemented. `config/capture.yaml` owns thresholds, intervals, trigger keys and storage decisions. Configuring a replay source excludes concurrent browser frames.

The rolling buffer is six seconds and bounded by count. Selected automatic/manual-stream frames are stored under `data/photos/auto` only if they produce facts or a label flag, and only after CPU Haar face detection and blur. Missing/broken OpenCV fails closed: facts can remain, but no image is retained. Set `privacy.store: none` for no image retention. Haar detection can miss faces; this is not an anonymization guarantee. Aim at equipment and inspect retained evidence before any demonstration sharing. Disk retention follows the existing evidence lifecycle; no new automatic evidence-deletion policy is introduced.

Optional face blur was checked with `opencv-python-headless==5.0.0.93`, installed using `pip install --no-deps` after a dry run. NumPy (2.5.2) and the installed PyTorch package version (2.14.0+cu130) were unchanged; PyTorch was not imported for that check. Do not let a dependency installation replace the shared environment's numerical packages.

## Synthetic replay (approved instance only)

Synthetic props live in `scenarios/frames/auto_capture/`; their values are versioned in `specs.json`. Re-render with `python scripts/render_capture_demo.py` (PIL only). The form is a synthetic sample, not an authenticated medical order. Nothing in this folder depicts a real patient.

```bash
python scripts/replay.py scenarios/auto_capture_demo.json --url http://localhost:8101
```

Use only your own approved instance: replay creates an incident. It holds one persistent camera socket while speech is submitted, respects real frame/rate intervals, then turns auto off. `--fast` is rejected for frame scenarios. `--no-llm` disables speech extraction only; it does **not** disable vision and is not a safe substitute for injected fakes during the training gate.

Watch the monitor update, then inspect the Narcan/ondansetron mismatch. The form remains unconfirmed. The last step exercises Show Herald; the medic can also use the on-screen button. Never present these synthetic/fake checks as real-model acceptance.

## Acceptance still required

Rajeev: ROI interaction sign-off and permission to use the serving model. Then run S9's three repetitions: monitor latency ≤20 s, rate bound, unchanged suppression, 5/5 mismatches and matches, speech p95 within 10%, retained-image face-blur spot check, and the guarded 30-minute soak. Report each run and its spread. Physical rear-camera permission, portrait/landscape ROI alignment and target-hardware usability remain pending. Desktop Chromium layout checks are complete; they do not substitute for those hands-on checks.
