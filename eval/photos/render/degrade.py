"""Phone-photo degradations, each a pure function (image, params, fields, rng) -> image. The canonical order is
fixed (ORDER) so that e.g. a thumb or a glare spot lands on the flat device before the camera tilts."""
from __future__ import annotations

import io
import random

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ORDER = ("occlusion", "moire", "glare", "perspective", "rotation", "blur", "motion_blur", "low_light", "jpeg")


def occlusion(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    """A thumb over one field (`p['field']`): a rounded finger entering from the nearest image edge, as thick as
    the field (within thumb-like bounds) and ending just past it."""
    x0, y0, x1, y1 = fields[p["field"]]
    w, h = img.size
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    edge = min((cx, "left"), (w - cx, "right"), (cy, "top"), (h - cy, "bottom"))[1]
    horizontal = edge in ("left", "right")
    across = (y1 - y0) if horizontal else (x1 - x0)
    t = min(max(across * 1.8, 110), 300) / 2
    m = 0.5 * t
    if edge == "left":
        box = [-t, cy - t, x1 + m, cy + t]
    elif edge == "right":
        box = [x0 - m, cy - t, w + t, cy + t]
    elif edge == "top":
        box = [cx - t, -t, cx + t, y1 + m]
    else:
        box = [cx - t, y0 - m, cx + t, h + t]
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    d.rounded_rectangle(box, int(t), fill=(214, 160, 130, 255))
    nail = {"left": [x1 - 1.1 * t, cy - 0.6 * t, x1 - 0.1 * t, cy + 0.6 * t],
            "right": [x0 + 0.1 * t, cy - 0.6 * t, x0 + 1.1 * t, cy + 0.6 * t],
            "top": [cx - 0.6 * t, y1 - 1.1 * t, cx + 0.6 * t, y1 - 0.1 * t],
            "bottom": [cx - 0.6 * t, y0 + 0.1 * t, cx + 0.6 * t, y0 + 1.1 * t]}[edge]
    d.rounded_rectangle(nail, int(0.4 * t), fill=(232, 192, 170, 255))
    over = over.filter(ImageFilter.GaussianBlur(3))
    out = img.convert("RGBA")
    out.alpha_composite(over)
    return out.convert("RGB")


def moire(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    """A screen photographed by a camera: interference bands between the display's pixel grid and the sensor
    (a sinusoid of `period` px at `angle` degrees, depth `strength`) and a faint RGB pixel grid."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = np.deg2rad(p.get("angle", 12))
    band = 0.5 * (1 + np.sin(2 * np.pi * (xx * np.cos(a) + yy * np.sin(a)) / p.get("period", 9)))
    shade = 1 - p.get("strength", 0.2) * band
    grid = np.ones((h, w, 3), dtype=np.float32)
    for c in range(3):
        grid[:, c::3, c] *= 1.06
    grid[1::3, :, :] *= 0.94
    arr = np.asarray(img, dtype=np.float32) * shade[..., None] * grid
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def glare(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    """A specular highlight: a soft white ellipse at relative position `at`, radius `size` of the width."""
    w, h = img.size
    cx, cy = p["at"][0] * w, p["at"][1] * h
    r = p["size"] * w
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = ((xx - cx) / r) ** 2 + ((yy - cy) / (0.6 * r)) ** 2
    a = (np.exp(-dist * 2.2) * p.get("strength", 0.7))[..., None]
    arr = np.asarray(img, dtype=np.float32)
    return Image.fromarray(np.clip(arr * (1 - a) + 255 * a, 0, 255).astype(np.uint8))


def _perspective_coeffs(src, dst):
    """Coefficients for Image.transform(PERSPECTIVE) mapping output points `dst` to input points `src`."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    return np.linalg.solve(np.array(rows, dtype=np.float64), np.array(rhs, dtype=np.float64)).tolist()


def perspective(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    """Camera held at an angle: the corners move inward by up to `strength` of the size, one side more."""
    w, h = img.size
    s = p["strength"]
    j = lambda: rng.uniform(0.3, 1.0) * s
    dst = [(0, 0), (w, 0), (w, h), (0, h)]
    src = [(-j() * w, -j() * h * 0.5), (w + j() * w * 0.4, -j() * h * 0.2), (w + j() * w * 0.2, h + j() * h * 0.4),
           (-j() * w * 0.6, h + j() * h * 0.6)]
    return img.transform(img.size, Image.PERSPECTIVE, _perspective_coeffs(src, dst), Image.BICUBIC,
                         fillcolor=(60, 60, 60))


def rotation(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    out = img.rotate(p["angle"], Image.BICUBIC, expand=True, fillcolor=(70, 68, 66))
    scale = max(img.size) / max(out.size)
    return out.resize((int(out.width * scale), int(out.height * scale)), Image.LANCZOS)


def blur(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(p["radius"]))


def motion_blur(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    """Hand shake: the average of `length` horizontally shifted copies."""
    n = int(p["length"])
    arr = np.asarray(img, dtype=np.float32)
    acc = np.zeros_like(arr)
    for k in range(n):
        acc += np.roll(arr, k - n // 2, axis=1)
    return Image.fromarray(np.clip(acc / n, 0, 255).astype(np.uint8))


def low_light(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    """A dim room: brightness scaled to `level`, a warm cast, and sensor noise."""
    dim = ImageEnhance.Brightness(img).enhance(p["level"])
    arr = np.asarray(dim, dtype=np.float32) * np.array([1.0, 0.93, 0.8], dtype=np.float32)
    noise = np.random.default_rng(rng.randrange(2 ** 31)).normal(0, 7, arr.shape)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


def jpeg(img: Image.Image, p: dict, fields: dict, rng: random.Random) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=int(p["quality"]))
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


FUNCS = {f.__name__: f for f in (occlusion, moire, glare, perspective, rotation, blur, motion_blur, low_light, jpeg)}


def apply(img: Image.Image, steps: list[dict], fields: dict, rng: random.Random) -> Image.Image:
    for step in sorted(steps, key=lambda s: ORDER.index(s["kind"])):
        img = FUNCS[step["kind"]](img, step, fields, rng)
    return img
