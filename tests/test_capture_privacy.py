from herald.capture.config import capture_config
from herald.capture.privacy import EvidenceStore
from test_capture_gate import frame


def test_only_used_redacted_frames_are_stored(tmp_path):
    called = []
    def blur(raw):
        called.append(raw)
        return b"redacted"
    store = EvidenceStore(tmp_path, capture_config()["privacy"], blur)
    f = frame()
    assert store.store(f, used=False) is None
    assert not list(tmp_path.rglob("*.jpg")) and not called
    photo = store.store(f, used=True)
    assert (tmp_path / "auto" / f"{photo}.jpg").read_bytes() == b"redacted"
    assert called == [f.jpeg]


def test_redaction_failure_never_saves_original(tmp_path):
    def unavailable(raw):
        raise RuntimeError("no cv2")
    store = EvidenceStore(tmp_path, capture_config()["privacy"], unavailable)
    assert store.store(frame(), used=True) is None
    assert not list(tmp_path.rglob("*.jpg"))


def test_detected_box_is_blurred_before_encoding():
    import pytest
    cv = pytest.importorskip("cv2")
    import numpy as np
    from herald.capture.privacy import FaceBlur
    class Detector:
        def detectMultiScale(self, image, **kwargs):
            return [(20, 20, 100, 100)]
    blur = FaceBlur(capture_config()["privacy"])
    blur.detector = Detector()
    raw = frame().jpeg
    result = blur(raw)
    original = cv.imdecode(np.frombuffer(raw, dtype=np.uint8), cv.IMREAD_GRAYSCALE)
    redacted = cv.imdecode(np.frombuffer(result, dtype=np.uint8), cv.IMREAD_GRAYSCALE)
    assert redacted[30:110, 30:110].var() < original[30:110, 30:110].var() / 10
