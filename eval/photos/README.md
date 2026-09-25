# Synthetic photo test set

`make_photos.py` renders every item in `specs.yaml` into `<id>.jpg` and writes `gold.jsonl`. Gold facts come only from the rendering parameters, never from a model. Every item has its own random stream (seed + id), so adding items never changes the existing images. The 43 rendered originals were checked byte-for-byte when the `screens` set was added. The renderers are in `render/`: `displays.py` (clinical devices), `wearables.py` (watch faces, wrist cuff), `apps.py` (phone app screens, a tablet showing a monitor), `documents.py`, `scene.py`, `icons.py`, and `degrade.py` (phone-photo degradations, including `moire` for a screen photographed by a camera).

```bash
~/miniforge3/envs/zgx/bin/python eval/photos/make_photos.py --sheet /tmp/sheet.jpg
~/miniforge3/envs/zgx/bin/python eval/vision_bench.py --model qwen3vl-fp8 --runs 3 --tasks photos
```

## Sets (gold `set`; the bench reports each one on its own under `per_set`)
| Set | Images | What it tests |
|---|---|---|
| `core` (no `set` field) | 45 | Bedside and defibrillator monitors, fingertip oximeters, BP cuffs, glucometers, pill labels, POLST forms, scenes, and distractors, with blur, glare, tilt, low light, JPEG and occlusion. |
| `screens` (added 2026-09-24) | 12 | Screens the monitor prompt was never tuned on: smartwatches, phone health, glucose, thermometer and fitness apps, a wrist BP cuff, and a tablet photo of a monitor. |

### The `screens` images and their gold
| Image | Shows | Gold |
|---|---|---|
| `watch_01_round_hr` | Round watch face: heart icon, 72, BPM, and the clock (no "heart rate" label). | hr 72 |
| `watch_02_rect_spo2` | Rectangular watch, Blood Oxygen app, 97%. | spo2 97 |
| `watch_03_ecg_result` | Watch ECG result: "Sinus Rhythm", "78 BPM Average", "30 s recording complete" (JPEG). | hr 78 |
| `watch_04_round_hr_resting_tilt` | Heart Rate 118 BPM with "Resting 64 BPM" below it (glare, tilt). | hr 118 |
| `phone_01_health_summary` | Health summary: latest HR 88, blood oxygen 95%, BP 128/82, plus steps, active energy, resting HR 61, sleep, and battery 64%. | hr 88, spo2 95, sbp 128, dbp 82 |
| `phone_02_hr_week_tilt` | Heart-rate detail: a "RANGE 58-142 BPM" header, a 7-day chart, Latest 104, Resting 66, Average 82 (tilt). | hr 104 |
| `phone_03_dark_vitals` | Dark app: heart rate 96, SpO2 93%, breathing rate 22, skin temperature +0.4 °C vs. baseline, HRV 28 ms, steps, battery 31% (JPEG). | hr 96, spo2 93, rr 22 |
| `phone_04_cgm_glucose_rot` | Glucose (CGM) app: 142 mg/dL with a trend arrow, a 3-hour chart with 70/180/250 lines, time in range 78%, 14-day average 151 (rotated). | glucose 142 |
| `phone_05_fitness_only` | Fitness app: steps, distance, calories, active minutes, floors, goals, battery. | none |
| `phone_06_thermometer_dim` | Thermometer app: 101.3 °F now, "Fever above 100.4 °F", and a history list 99.1 / 98.7 / 98.4 °F (dim room). | temp 38.5 |
| `bpcuff_wrist_01_glare` | Wrist cuff: SYS 146, DIA 92, and a pulse of 88 marked only by a heart icon and /min, plus date, time and memory slot M 12 (glare). | sbp 146, dbp 92, hr 88 |
| `screen_01_tablet_monitor_angle` | A tablet showing a picture of a bedside monitor, photographed at an angle with moiré and glare. | hr 110, spo2 94, sbp 138, dbp 86, rr 22, temp 37.8 |

### Labeling rules for screens
The same rules are in the header of the `screens` block in `specs.yaml`. Normalization follows `docs/LABELING_GUIDE.md` §4.
- **Counts as the current reading:** the single most recent value of a measurement, shown as its main number or marked "Latest", "Now" or "just now". The result of a measurement just taken also counts: a watch ECG's heart rate is the rate over that 30 s recording, even though the screen calls it "Average", and a cuff's result counts too.
- **Does not count:** resting heart rate; daily or weekly averages; min-max ranges; charts and trends; goals, targets and thresholds (a CGM target band, a fever threshold); earlier entries in a history list; a change from a personal baseline (skin temperature variation); HRV; time in range; and anything that is not a vital (clock, date, battery %, steps, distance, calories, sleep, floors, active minutes, memory-slot numbers).
- A rhythm label such as "Sinus Rhythm" is not a fact. Herald reads numbers from photos and does not interpret ECGs.
- Temperature is recorded in Celsius with one decimal, so 101.3 °F is gold 38.5.

## Results (qwen3vl-fp8, 3 runs each)
Before the change (monitor prompt v1, which lists clinical devices), the model read all 12 `screens` images exactly in every run. The core set was 42/45 in every run. The live device-agnostic prompt (v5) gave 42, 41 and 42 on core and 12, 11 and 12 on `screens`: a tie within run-to-run noise. The full comparison is in `docs/MODEL_PLAN.md` §2a, covering five prompt versions, their failure causes, and the methodology notes (which versions were written before and which after seeing results, and the concurrent load).
