"""Every target must be what the product accepts: each one is fed through the real VisionReader (as if the model
had answered exactly the target) with the real RxNorm coder, and must come out unchanged: no fact dropped by the
photo plausibility ranges or the SBP/DBP check, every value valid for the vocabulary, and every drug name an exact
RxNorm match to its own value (so the target never relies on fuzzy or phonetic matching)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from herald.core.vocabulary import default_vocabulary
from herald.models import VisionReader


class _Answer:
    """A stand-in vision model that answers with a fixed JSON object."""

    def __init__(self):
        self.answer: dict = {"facts": []}

    def available(self):
        return True

    def model_name(self):
        return "target-check"

    def chat_json(self, system, user, **kw):
        return json.loads(json.dumps(self.answer))


class ReaderCheck:
    def __init__(self, index_path: Optional[Path] = None):
        vocab = default_vocabulary()
        coder = None
        if index_path and Path(index_path).exists():
            from herald.terminology.factory import build_coder
            from herald.terminology.rxnorm import RxNormNormalizer
            from herald.config import get_settings
            coder = build_coder(get_settings(), vocab, RxNormNormalizer.load(Path(index_path)))
        self.model = _Answer()
        self.reader = VisionReader(self.model, coder)
        self.vocab = vocab
        self.coded = coder is not None

    def problems(self, mode: str, target: dict) -> list[str]:
        self.model.answer = target
        out = self.reader.read(b"x", mode, photo_id="check")
        errs = []
        want = [(f["key"], f["value"]) for f in target["facts"]]
        got = [(f.key, f.value) for f in out if f.key in {k for k, _ in want}]
        if sorted(map(str, want)) != sorted(map(str, got)):
            errs.append(f"reader changed facts: {want} -> {got}")
        for f in target["facts"]:
            try:
                self.vocab.validate(f["key"], f["value"])
            except ValueError as e:
                errs.append(str(e))
        if self.coded:
            for f in out:
                if f.key == "meds.list":
                    for entry in (f.provenance.normalized or []):
                        if entry["method"] != "exact" or entry["value"] != entry["said"]:
                            errs.append(f"drug not an exact self-match: {entry}")
        return errs

    def run(self, recs: list[dict]) -> dict:
        failures = []
        for r in recs:
            errs = self.problems(r["mode"], json.loads(r["target"]))
            if errs:
                failures.append({"id": r["id"], "errors": errs[:3]})
        return {"checked": len(recs), "coded_with_rxnorm": self.coded, "failures": len(failures),
                "examples": failures[:10]}
