#!/usr/bin/env python
"""Would the frame gate fire on a camera pointed at a screen showing a patient monitor?

Pure CPU: no model, no camera, no GPU. Two modes:

  synthetic  (default)  render a photo of a laptop showing a monitor UI, change one or more vitals, and run the
                        real FrameGate (herald/capture/gate.py) over the pair, full-frame and with an ROI.
  real       --image A --image B, or --dir DIR
                        run the same gate over real captured frames, in filename order, so the shipped numbers can
                        be retuned against the mounted camera.

WHY SYNTHETIC NUMBERS UNDERSTATE `change`: a rendered pair differs only in the pixels of the digits that changed.
A real camera adds sensor noise, auto-exposure drift, rolling-shutter banding and small hand/vehicle motion to
EVERY pixel, so the same vital change measures a LARGER mean absolute difference on real frames than it does here.
Treat the synthetic values as a floor: a threshold that a synthetic single-vital change clears will also clear on
the camera; one it fails may still fire in the vehicle. Tune with --dir against real frames before believing a
value in the field.

Run:
  PY=~/miniforge3/envs/zgx/bin/python
  $PY scripts/capture/gate_probe.py                       # synthetic sweep, both gate profiles
  $PY scripts/capture/gate_probe.py --dir data/frames/monitor --roi 0.22,0.22,0.78,0.78
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from PIL import Image, ImageDraw, ImageFont            # noqa: E402

from herald.capture.config import capture_config, monitor_gate_config   # noqa: E402
from herald.capture.gate import FrameGate              # noqa: E402
from herald.capture.types import Frame, ROI            # noqa: E402

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(size: int):
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def monitor_photo(hr, sbp, dbp, spo2, rr, *, dark=True, width=1280, height=800, screen_frac=0.55):
    """A photo of a laptop: textured room background plus a screen showing a vitals-monitor UI."""
    room = Image.new("RGB", (width, height), (78, 74, 70))
    draw = ImageDraw.Draw(room)
    for y in range(0, height, 24):                      # mild room texture, so sharpness is realistic
        draw.line([(0, y), (width, y)], fill=(88, 84, 80), width=1)
    sw, sh = int(width * screen_frac), int(height * screen_frac)
    screen = Image.new("RGB", (sw, sh), (8, 10, 14) if dark else (244, 245, 248))
    d = ImageDraw.Draw(screen)
    label_ink = (150, 160, 170) if dark else (90, 95, 105)
    rows = [("HR", f"{hr}", (90, 230, 120)), ("NIBP", f"{sbp}/{dbp}", (250, 225, 90)),
            ("SpO2", f"{spo2}", (120, 200, 255)),
            ("RR", f"{rr}", (255, 255, 255) if dark else (30, 30, 30))]
    y = int(sh * 0.06)
    for label, value, colour in rows:
        d.text((int(sw * 0.06), y), label, font=font(max(11, int(sh * 0.045))), fill=label_ink)
        d.text((int(sw * 0.30), y - int(sh * 0.012)), value, font=font(max(18, int(sh * 0.17))),
               fill=colour if dark else tuple(int(c * 0.55) for c in colour))
        y += int(sh * 0.23)
    room.paste(screen, ((width - sw) // 2, (height - sh) // 2))
    return room, ((width - sw) // 2, (height - sh) // 2, sw, sh)


def jpeg(image: Image.Image, quality=85) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def as_frame(image: Image.Image, frame_id="f", ts=0.0) -> Frame:
    return Frame(id=frame_id, jpeg=jpeg(image), w=image.width, h=image.height, ts=ts, source="probe")


def roi_from_box(box, width, height, pad=0.0) -> ROI:
    x, y, w, h = box
    return ROI(max(0.0, x / width - pad), max(0.0, y / height - pad),
               min(1.0, (x + w) / width + pad), min(1.0, (y + h) / height + pad))


def parse_roi(text: str | None) -> ROI | None:
    if not text:
        return None
    x0, y0, x1, y1 = (float(part) for part in text.split(","))
    return ROI(x0, y0, x1, y1)


def pair(profile: dict, name: str, first: Frame, second: Frame, roi: ROI | None, thresholds: dict) -> dict:
    """Baseline on `first` (the gate's first look), then assess `second` exactly as the agent would."""
    gate = FrameGate(profile)
    gate.accept(first, roi)
    r = gate.assess(second, roi)
    verdict = ("PASS" if r.passed else
               f"FAIL:{r.reason}" + ("" if r.usable else " (unusable: monitor_refresh can never run either)"))
    print(f"  {name:<44s} bright {r.bright:6.1f}  sharp {r.sharp:8.1f}  change {r.changed:.5f}  "
          f"usable {str(r.usable):<5s} {verdict}")
    if not r.passed and r.usable and r.changed < thresholds["change_min"]:
        print(f"  {'':<44s} -> change_min would have to be <= {r.changed:.4f} to admit this")
    return {"bright": r.bright, "sharp": r.sharp, "change": r.changed, "usable": r.usable, "passed": r.passed}


def header(title: str, profile: dict) -> None:
    print(f"\n=== {title} ===")
    print(f"    bright {profile['bright_min']}..{profile['bright_max']}  sharp >= {profile['sharp_min']}  "
          f"change >= {profile['change_min']}  (gate width {profile['width']})")


def synthetic(profiles: dict[str, dict]) -> None:
    width, height = 1280, 800
    for title, profile in profiles.items():
        header(f"synthetic renders, {title} profile", profile)
        for dark in (True, False):
            tag = "dark monitor UI" if dark else "white monitor UI"
            first, box = monitor_photo(96, 140, 88, 95, 18, dark=dark, width=width, height=height)
            one, _ = monitor_photo(96, 168, 94, 95, 18, dark=dark, width=width, height=height)   # BP 140 -> 168
            many, _ = monitor_photo(124, 168, 94, 91, 24, dark=dark, width=width, height=height)  # four vitals move
            print(f"  -- {tag}")
            a, b = as_frame(first, "a"), as_frame(one, "b", 1.0)
            c = as_frame(many, "c", 2.0)
            screen = roi_from_box(box, width, height)
            x, y, w, h = box
            tight = roi_from_box((x + int(w * 0.25), y + int(h * 0.21), int(w * 0.55), int(h * 0.22)), width, height)
            pair(profile, "full frame, one vital (BP 140->168)", a, b, None, profile)
            pair(profile, "ROI=screen, one vital (BP 140->168)", a, b, screen, profile)
            pair(profile, "ROI=screen, four vitals move", a, c, screen, profile)
            pair(profile, "ROI=NIBP row only, one vital", a, b, tight, profile)


def real(paths: list[Path], profiles: dict[str, dict], roi: ROI | None) -> None:
    if len(paths) < 2:
        raise SystemExit("need at least two frames: pass --image twice, or --dir with two or more images")
    for title, profile in profiles.items():
        header(f"real frames, {title} profile ({len(paths)} images)", profile)
        for index in range(1, len(paths)):
            with Image.open(paths[index - 1]) as first_image, Image.open(paths[index]) as second_image:
                first = as_frame(first_image.copy(), paths[index - 1].name, float(index - 1))
                second = as_frame(second_image.copy(), paths[index].name, float(index))
            pair(profile, f"{paths[index - 1].name} -> {paths[index].name}", first, second, roi, profile)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", action="append", default=[], type=Path,
                   help="a real captured frame; pass twice or more, in time order")
    p.add_argument("--dir", type=Path, help="a directory of real captured frames, compared in filename order")
    p.add_argument("--roi", help="normalized ROI for real frames: x0,y0,x1,y1 (default: the whole frame)")
    p.add_argument("--profile", choices=("global", "monitor", "both"), default="both",
                   help="which gate profile to report (default both)")
    args = p.parse_args()

    config = capture_config()
    available = {"global": config["gate"], "monitor": monitor_gate_config(config)}
    profiles = available if args.profile == "both" else {args.profile: available[args.profile]}

    paths = list(args.image)
    if args.dir:
        paths += sorted(path for path in args.dir.iterdir()
                        if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"))
    if paths:
        real(paths, profiles, parse_roi(args.roi))
    else:
        synthetic(profiles)
    print("\nSynthetic renders understate `change`: only the changed digits differ. A real camera adds noise,"
          "\nexposure drift and small motion to every pixel, so the same change measures higher in the vehicle."
          "\nRetune with --dir against real frames before trusting any value in the field.")


if __name__ == "__main__":
    main()
