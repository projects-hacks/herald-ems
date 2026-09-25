"""Store used evidence only, after face redaction. Missing detector fails closed (no file)."""
from pathlib import Path

import numpy as np

from ..core.schema import new_id


class FaceBlur:
    def __init__(self, config: dict):
        self.config = config
        self.detector = None
        self.cv = None
        try:
            import cv2
            self.cv = cv2
            self.detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            if self.detector.empty():
                self.detector = None
        except (ImportError, AttributeError, RuntimeError):
            pass

    @property
    def available(self):
        return self.detector is not None

    def __call__(self, jpeg: bytes) -> bytes:
        if not self.available:
            raise RuntimeError("face detector unavailable: evidence storage disabled")
        cv, c = self.cv, self.config
        image = cv.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv.IMREAD_COLOR)
        if image is None:
            raise ValueError("invalid evidence image")
        grey = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
        boxes = self.detector.detectMultiScale(grey, scaleFactor=c["scale_factor"], minNeighbors=c["min_neighbors"],
                                              minSize=(c["min_face_px"], c["min_face_px"]))
        for x, y, w, h in boxes:
            image[y:y+h, x:x+w] = cv.GaussianBlur(image[y:y+h, x:x+w], (0, 0), c["blur_sigma"])
        ok, encoded = cv.imencode(".jpg", image)
        if not ok:
            raise ValueError("could not encode redacted evidence")
        return encoded.tobytes()


class EvidenceStore:
    def __init__(self, photo_dir: Path, config: dict, blur):
        self.directory, self.config, self.blur = photo_dir / config["dir"], config, blur

    def store(self, frame, *, used: bool) -> str | None:
        if not used or self.config["store"] == "none" or not self.config["blur_faces"]:
            return None
        try:
            redacted = self.blur(frame.jpeg)
        except Exception:
            return None
        photo_id = new_id("auto")
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{photo_id}.jpg").write_bytes(redacted)
        return photo_id
