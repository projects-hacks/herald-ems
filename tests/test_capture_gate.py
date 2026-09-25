import io

import numpy as np
import pytest
from PIL import Image, ImageFilter

from herald.capture.buffer import FrameBuffer
from herald.capture.config import capture_config, validate_config
from herald.capture.frames import decode_frame
from herald.capture.gate import FrameGate
from herald.capture.types import ROI


def frame(ts=0, *, offset=0, blur=False, brightness=None):
    array = np.indices((160, 240)).sum(axis=0) // 8 % 2 * 150 + 50
    array = np.roll(array, offset, axis=1).astype(np.uint8)
    if brightness is not None:
        array[:] = brightness
    im = Image.fromarray(array)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(8))
    b = io.BytesIO(); im.save(b, "JPEG")
    return decode_frame(b.getvalue(), ts, "test", capture_config())


def test_quality_and_accepted_baseline():
    gate = FrameGate(capture_config()["gate"])
    first = frame()
    assert gate.assess(first).passed
    assert gate.assess(first).passed  # assessing does not accept the baseline
    gate.accept(first)
    assert gate.assess(first).reason == "unchanged"
    assert gate.assess(frame(offset=7)).passed
    assert gate.assess(frame(blur=True)).reason == "blurred"
    assert gate.assess(frame(brightness=0)).reason == "dark"
    assert gate.assess(frame(brightness=255)).reason == "bright"


def test_roi_ignores_changes_outside_monitor():
    c = capture_config(); gate = FrameGate(c["gate"]); original = frame()
    roi = ROI(0, 0, .5, 1); gate.accept(original, roi)
    with Image.open(io.BytesIO(original.jpeg)) as im:
        im.paste(0, (130, 0, 240, 160)); b = io.BytesIO(); im.save(b, "JPEG")
    changed = decode_frame(b.getvalue(), 1, "test", c)
    assert not gate.assess(changed, roi).passed
    assert gate.assess(frame(offset=7), roi).passed


def test_buffer_is_time_and_count_bounded_manual_bypasses_quality():
    buffer = FrameBuffer(6, 3); gate = FrameGate(capture_config()["gate"])
    for i in range(10):
        f = frame(i, blur=True); buffer.add(f, gate.assess(f))
    assert len(buffer.items) == 3
    assert buffer.best(7, 9) is None
    assert buffer.best(7, 9, manual=True) is not None
    buffer.prune(16)
    assert not buffer.items


def test_frame_limits_and_roi_validation():
    c = capture_config()
    with pytest.raises(ValueError):
        decode_frame(b"x" * (c["max_frame_bytes"] + 1), 0, "test", c)
    with pytest.raises(ValueError):
        ROI(0.5, 0, 0.2, 1)
    c["buffer_s"] = -1
    with pytest.raises(ValueError):
        validate_config(c)
