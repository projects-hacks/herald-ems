"""Photographing a rendered panel: placement with perspective, rotation and crop, background clutter, fingers,
glare, blur, low light, noise and JPEG. Every geometric step is one homography, so each reading's box is mapped
into the photo exactly; an occluder or glare that hides most of a reading marks it unreadable (it leaves the
target), and one that would half-hide a value is moved away instead, so no target is ambiguous."""
from __future__ import annotations

import io
import math
from random import Random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import canvas as cv
from .spec import Box, Example, Panel

HIDE_AT = 0.40          # a reading at least this covered is unreadable (omitted from the target)
SAFE_BELOW = 0.06
HIDE_SHARE = 0.25       # of fingers (and half that of glare spots) aimed at a reading to hide it       # a random occluder must cover less than this of every reading, or it is moved
NOISE_WORDS = ["KITCHEN", "SALE", "Tuesday", "notes", "PARKING", "WiFi", "ROOM 4", "Thank you", "OPEN", "12 oz",
               "MENU", "fragile", "EXIT", "remote", "coffee", "mail", "keys", "LOT 7", "B-2", "FRONT"]


# ---------- geometry ----------
def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> np.ndarray:
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    h = np.linalg.solve(np.array(a, float), np.array(b, float))
    return np.append(h, 1).reshape(3, 3)


def apply(h: np.ndarray, pts) -> np.ndarray:
    p = np.hstack([np.asarray(pts, float), np.ones((len(pts), 1))]) @ h.T
    return p[:, :2] / p[:, 2:3]


def map_box(h: np.ndarray, box: Box) -> Box:
    x0, y0, x1, y1 = box
    q = apply(h, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max())


def _placement(rng: Random, pw: int, ph: int, ow: int, oh: int, rot_deg: float, fill: float, persp: float):
    """Destination quad of the panel in the photo, and its homography."""
    s = fill * min(ow / pw, oh / ph)
    cx = ow / 2 + rng.uniform(-0.12, 0.12) * ow
    cy = oh / 2 + rng.uniform(-0.12, 0.12) * oh
    t = math.radians(rot_deg)
    quad = []
    for x, y in [(0, 0), (pw, 0), (pw, ph), (0, ph)]:
        dx, dy = (x - pw / 2) * s, (y - ph / 2) * s
        u = cx + dx * math.cos(t) - dy * math.sin(t)
        v = cy + dx * math.sin(t) + dy * math.cos(t)
        quad.append((u + rng.uniform(-persp, persp) * pw * s, v + rng.uniform(-persp, persp) * ph * s))
    return quad, homography([(0, 0), (pw, 0), (pw, ph), (0, ph)], quad)


# ---------- backgrounds and occluders ----------
def background(rng: Random, size: tuple[int, int]) -> Image.Image:
    w, h = size
    base = tuple(rng.randint(20, 235) for _ in range(3))
    im = Image.new("RGB", size, base)
    d = ImageDraw.Draw(im)
    style = rng.choice(["wood", "fabric", "clutter", "plain", "clutter"])
    if style == "wood":
        for y in range(0, h, rng.randint(3, 7)):
            d.line([(0, y), (w, y + rng.randint(-8, 8))], fill=cv.jitter(rng, base, 22), width=rng.randint(1, 4))
    elif style == "fabric":
        arr = np.asarray(im, np.int16) + np.random.default_rng(rng.randint(0, 2**31)).integers(-25, 25, (h, w, 1))
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im)
    if style in ("clutter", "wood"):
        for _ in range(rng.randint(3, 12)):
            col = tuple(rng.randint(0, 255) for _ in range(3))
            x, y = rng.uniform(-0.1, 1) * w, rng.uniform(-0.1, 1) * h
            sw, sh = rng.uniform(0.05, 0.4) * w, rng.uniform(0.05, 0.4) * h
            shape = rng.choice(["rect", "ellipse", "line", "word"])
            if shape == "rect":
                d.rectangle([x, y, x + sw, y + sh], fill=col)
            elif shape == "ellipse":
                d.ellipse([x, y, x + sw, y + sh], fill=col)
            elif shape == "line":
                d.line([(x, y), (x + sw, y + sh)], fill=col, width=rng.randint(2, 12))
            else:
                cv.text(d, (x, y), rng.choice(NOISE_WORDS), cv.pick_font(rng, "sans"), rng.randint(14, 40), col)
    shade = Image.linear_gradient("L").resize(size).rotate(rng.uniform(0, 360))
    return Image.composite(im, Image.new("RGB", size, (0, 0, 0)), shade.point(lambda v: 150 + v * 105 // 255))


def finger(rng: Random, size: tuple[int, int], target: Box | None, scale: float) -> tuple[Image.Image, Image.Image]:
    """A fingertip or thumb: returns (RGBA layer, damage mask L)."""
    w, h = size
    skin = rng.choice([(233, 190, 160), (198, 146, 110), (141, 95, 66), (95, 62, 42), (224, 172, 140), (170, 120, 90)])
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    width = scale * rng.uniform(0.9, 1.4)
    if target:
        tx, ty = (target[0] + target[2]) / 2, (target[1] + target[3]) / 2
    else:
        edge = rng.choice(["left", "right", "top", "bottom"])
        tx = {"left": 0.02, "right": 0.98}.get(edge, rng.uniform(0.1, 0.9)) * w
        ty = {"top": 0.02, "bottom": 0.98}.get(edge, rng.uniform(0.1, 0.9)) * h
    ang = rng.uniform(0, 2 * math.pi)
    ex, ey = tx + math.cos(ang) * w * 1.5, ty + math.sin(ang) * h * 1.5
    d.line([(tx, ty), (ex, ey)], fill=skin + (255,), width=int(width))
    d.ellipse([tx - width / 2, ty - width / 2, tx + width / 2, ty + width / 2], fill=skin + (255,))
    nail = width * 0.32
    d.ellipse([tx - nail, ty - nail, tx + nail, ty + nail], fill=cv.jitter(rng, (235, 205, 195), 10) + (200,))
    layer = layer.filter(ImageFilter.GaussianBlur(max(1, width * 0.04)))
    mask = layer.getchannel("A").point(lambda a: 255 if a > 128 else 0)
    return layer, mask


def glare(rng: Random, size: tuple[int, int], target: Box | None, strength: float) -> tuple[Image.Image, Image.Image]:
    """A specular highlight: returns (white alpha layer L, damage mask L where the content is washed out)."""
    w, h = size
    if target:
        cx, cy = (target[0] + target[2]) / 2, (target[1] + target[3]) / 2
        rx, ry = (target[2] - target[0]) * 1.3 + 20, (target[3] - target[1]) * 1.3 + 20
    else:
        cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.1, 0.9) * h
        rx, ry = rng.uniform(0.05, 0.25) * w, rng.uniform(0.03, 0.15) * h
    yy, xx = np.mgrid[0:h, 0:w]
    r = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    a = np.clip(strength * np.exp(-r * (0.5 if target else 1.2)), 0, 1)
    layer = Image.fromarray((a * 255).astype(np.uint8))
    return layer, Image.fromarray(((a > 0.85) * 255).astype(np.uint8))      # washed out: nothing left to read


def coverage(mask: Image.Image, box: Box) -> float:
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(mask.width, x1), min(mask.height, y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float(np.asarray(mask.crop((x0, y0, x1, y1)), np.float32).mean() / 255)


def _motion_blur(im: Image.Image, rng: Random, length: int) -> Image.Image:
    arr = np.asarray(im, np.float32)
    ang = rng.uniform(0, math.pi)
    acc = np.zeros_like(arr)
    for i in range(length):
        dx, dy = int(round(math.cos(ang) * (i - length / 2))), int(round(math.sin(ang) * (i - length / 2)))
        acc += np.roll(np.roll(arr, dx, axis=1), dy, axis=0)
    return Image.fromarray(np.clip(acc / length, 0, 255).astype(np.uint8))


# ---------- the photo ----------
def photograph(panel: Panel, rng: Random, example_id: str, hard: float = 0.5) -> Example:
    """`hard` (0..1) scales how many and how strong the effects are; 0 is a gentle photo (placement, perspective
    and background only: no fingers, glare, blur, low light or heavy JPEG)."""
    gentle = hard <= 0.0
    long_side = rng.choice([1024, 1024, 960, 896, 800])
    aspect = rng.choice([4 / 3, 3 / 4, 1.0, 16 / 9, 9 / 16, 3 / 4])
    ow, oh = (long_side, int(long_side / aspect)) if aspect >= 1 else (int(long_side * aspect), long_side)
    pw, ph = panel.image.size
    degr: list[str] = []
    sev = 0.0
    # --- geometry: rotation, perspective, fill, crop ---
    rot = rng.gauss(0, 6 * hard + 1)
    if not gentle and rng.random() < 0.12 * hard + 0.03:
        rot += rng.choice([90, -90, 180])
        degr.append("rotation")
        sev += 0.1
    elif abs(rot) > 8:
        degr.append("rotation")
    persp = rng.choice([0, 0, 0.03, 0.06, 0.1]) * (0.5 + hard)
    if persp >= 0.05:
        degr.append("perspective")
        sev += 0.1
    readings = [r for r in panel.readings if r.box]
    for _ in range(12):
        fill = rng.uniform(0.8, 1.05) if panel.flat else rng.uniform(0.55, 0.95)   # papers are shot close
        quad, h = _placement(rng, pw, ph, ow, oh, rot, fill, persp)
        boxes = [map_box(h, r.box) for r in readings]
        inside = all(b[0] >= 1 and b[1] >= 1 and b[2] <= ow - 1 and b[3] <= oh - 1 for b in boxes)
        min_h = min((min(b[2] - b[0], b[3] - b[1]) for b in boxes), default=99)
        if inside and min_h >= 12:
            break
    else:
        fill = 0.9
        quad, h = _placement(rng, pw, ph, ow, oh, rot % 90 if abs(rot) < 45 else rot, fill, 0)
    if any(q[0] < 0 or q[1] < 0 or q[0] > ow or q[1] > oh for q in quad):
        degr.append("crop")
    hinv = np.linalg.inv(h)
    coeffs = (hinv / hinv[2, 2]).flatten()[:8]
    warped = panel.image.transform((ow, oh), Image.Transform.PERSPECTIVE, tuple(coeffs), Image.Resampling.BICUBIC)
    photo = background(rng, (ow, oh))
    if not panel.flat and rng.random() < 0.6:        # device shadow
        sh = warped.getchannel("A").filter(ImageFilter.GaussianBlur(12))
        photo.paste((0, 0, 0), (rng.randint(4, 18), rng.randint(4, 18)), sh.point(lambda a: a * 0.5))
    photo.paste(warped, (0, 0), warped)
    mapped = {id(r): map_box(h, r.box) for r in readings}
    for r in readings:
        if r.strength_box:
            r.strength_box = map_box(h, r.strength_box)
    damage = Image.new("L", (ow, oh), 0)
    # --- fingers / thumbs (sometimes deliberately over one reading) ---
    visible = [r for r in readings if r.readable]
    scale = max(40, min(ow, oh) * rng.uniform(0.09, 0.16))
    if not gentle and rng.random() < 0.28 * hard + 0.05:
        hide = visible and rng.random() < HIDE_SHARE
        target = rng.choice(visible) if hide else None
        for _ in range(6):
            layer, mask = finger(rng, (ow, oh), mapped[id(target)] if target else None, scale)
            cov = {id(r): coverage(mask, mapped[id(r)]) for r in visible}
            ok = all(c < SAFE_BELOW or c >= HIDE_AT for c in cov.values()) and (target is None or cov[id(target)] >= HIDE_AT)
            if ok:
                photo.paste(layer, (0, 0), layer)
                damage = Image.fromarray(np.maximum(np.asarray(damage), np.asarray(mask)))
                degr.append("occlusion")
                sev += 0.1
                break
    # --- glare ---
    if not gentle and rng.random() < (0.35 if not panel.flat else 0.2) * (0.5 + hard):
        visible = [r for r in readings if r.readable and coverage(damage, mapped[id(r)]) < HIDE_AT]
        target = rng.choice(visible) if visible and rng.random() < HIDE_SHARE / 2 else None
        for _ in range(6):
            layer, mask = glare(rng, (ow, oh), mapped[id(target)] if target else None,
                                1.3 if target else rng.uniform(0.35, 0.95))
            cov = {id(r): coverage(mask, mapped[id(r)]) for r in visible}
            ok = all(c < SAFE_BELOW or c >= HIDE_AT for c in cov.values()) and (target is None or cov[id(target)] >= HIDE_AT)
            if ok:
                photo = Image.composite(Image.new("RGB", (ow, oh), (255, 255, 250)), photo, layer)
                damage = Image.fromarray(np.maximum(np.asarray(damage), np.asarray(mask)))
                degr.append("glare")
                sev += 0.1
                break
    for r in readings:
        b = mapped[id(r)]
        if r.readable and coverage(damage, b) >= HIDE_AT:
            r.readable, r.why_unreadable = False, "occluded"
        if r.strength_box and r.strength_readable and coverage(damage, r.strength_box) >= HIDE_AT:
            r.strength_readable = False
        r.box = (max(0.0, b[0] / ow), max(0.0, b[1] / oh), min(1.0, b[2] / ow), min(1.0, b[3] / oh))
        if r.strength_box:
            sb = r.strength_box
            r.strength_box = (sb[0] / ow, sb[1] / oh, sb[2] / ow, sb[3] / oh)
    # --- photometric effects (bounded so the readings stay legible) ---
    min_h = float(min((mapped[id(r)][3] - mapped[id(r)][1] for r in readings), default=60))
    if not gentle and rng.random() < 0.3 * (0.5 + hard):
        photo = photo.filter(ImageFilter.GaussianBlur(min(3.0, max(0.6, min_h * rng.uniform(0.03, 0.08)))))
        degr.append("blur")
        sev += 0.15
    elif not gentle and rng.random() < 0.15 * (0.5 + hard):
        photo = _motion_blur(photo, rng, max(2, min(9, int(min_h * rng.uniform(0.08, 0.2)))))
        degr.append("motion_blur")
        sev += 0.15
    if not panel.flat and rng.random() < 0.3:               # screen moire / scanlines
        arr = np.asarray(photo, np.float32)
        period = rng.randint(3, 7)
        arr *= (1 - 0.08 * (np.arange(oh) % period == 0))[:, None, None]
        photo = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if not gentle and rng.random() < 0.25 * (0.5 + hard):
        arr = np.asarray(photo, np.float32) / 255
        arr = arr ** rng.uniform(1.4, 2.2) * rng.uniform(0.45, 0.75)
        arr *= np.array([rng.uniform(0.9, 1.1), 1.0, rng.uniform(0.75, 1.0)])
        photo = Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8))
        degr.append("low_light")
        sev += 0.1
    if rng.random() < (0.1 if gentle else 0.4):
        arr = np.asarray(photo, np.float32)
        arr += np.random.default_rng(rng.randint(0, 2**31)).normal(0, rng.uniform(2, 9), arr.shape)
        photo = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        degr.append("noise")
    q = rng.randint(35, 70) if (not gentle and rng.random() < 0.3 * (0.5 + hard)) else rng.randint(78, 94)
    if q < 70:
        degr.append("jpeg")
        sev += 0.1
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=q)
    photo = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return Example(example_id, photo, panel, sorted(set(degr)), min(1.0, sev), jpeg=buf.getvalue())
