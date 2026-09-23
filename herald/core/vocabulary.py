"""The canonical key vocabulary (config/vocabulary.yaml) and the value rules that go with it."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import load_yaml

_EMPTY_LIST_WORDS = ("none", "nkda", "no known allergies", "")
_TRUE_WORDS = ("true", "yes", "y", "1", "witnessed", "on")


class Vocabulary:
    def __init__(self, keys: dict[str, dict], contradiction_keys: set[str]):
        self.keys = keys
        self.contradiction_keys = contradiction_keys

    @classmethod
    def from_config(cls, rel: str = "vocabulary.yaml") -> "Vocabulary":
        data = load_yaml(rel)
        keys = {k: {**v, **({"range": tuple(v["range"])} if "range" in v else {})} for k, v in data["keys"].items()}
        return cls(keys, set(data["contradiction_keys"]))

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def meta(self, key: str) -> dict:
        return self.keys[key]

    def label(self, key: str) -> str:
        return self.keys[key]["label"]

    def coerce(self, key: str, value: Any) -> Any:
        """Convert an extracted value to the key's declared type; ValueError if it can't be."""
        t = self.keys[key]["type"]
        if value is None:
            return None
        try:
            if t == "int":
                return int(round(float(value)))
            if t == "float":
                return round(float(value), 1)
            if t == "bool":
                return value.strip().lower() in _TRUE_WORDS if isinstance(value, str) else bool(value)
            if t == "list":
                if isinstance(value, str):
                    return [] if value.strip().lower() in _EMPTY_LIST_WORDS else [value.strip()]
                return [str(x).strip() for x in value]
            return str(value).strip()
        except (TypeError, ValueError):
            raise ValueError(f"cannot coerce {value!r} to {t} for {key}")

    def validate(self, key: str, value: Any) -> Any:
        """Coerce and check physical plausibility (a safety validator). Returns the coerced value."""
        if key not in self.keys:
            raise ValueError(f"unknown key {key}")
        v = self.coerce(key, value)
        bounds = self.keys[key].get("range")
        if bounds and v is not None and not (bounds[0] <= v <= bounds[1]):
            raise ValueError(f"implausible {key} {v!r}: outside {bounds[0]}-{bounds[1]}")
        return v


def norm_value(v: Any) -> Any:
    """Comparison form of a value: lists as sorted lowercase tuples, strings lowercase."""
    if isinstance(v, list):
        return tuple(sorted(str(x).strip().lower() for x in v))
    if isinstance(v, str):
        return v.strip().lower()
    return v


@lru_cache(maxsize=1)
def default_vocabulary() -> Vocabulary:
    return Vocabulary.from_config()
