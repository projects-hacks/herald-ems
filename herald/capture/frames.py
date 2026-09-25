"""Small bounded JPEG decode and crop helpers."""
import io

from PIL import Image

from ..core.schema import new_id
from .types import Frame, ROI


def decode_frame(raw: bytes, ts: float, source: str, config: dict) -> Frame:
    if not raw or len(raw) > config["max_frame_bytes"]:
        raise ValueError("frame exceeds byte limit")
    with Image.open(io.BytesIO(raw)) as im:
        if im.format != "JPEG" or max(im.size) > config["max_side"] or min(im.size) < 1:
            raise ValueError("send a JPEG within the configured dimension limit")
        im.verify()
        w, h = im.size
    return Frame(new_id("frame"), ts, raw, w, h, source)


def cropped(frame: Frame, roi: ROI | None, margin: float) -> bytes:
    if roi is None:
        return frame.jpeg
    with Image.open(io.BytesIO(frame.jpeg)) as im:
        im = im.convert("RGB").crop(roi.box(frame.w, frame.h, margin))
        out = io.BytesIO()
        im.save(out, "JPEG")
        return out.getvalue()
