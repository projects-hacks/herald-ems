"""The canonical key vocabulary (config/vocabulary.yaml) and the value rules that go with it."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from ..config import load_yaml

_EMPTY_LIST_WORDS = ("none", "nkda", "no known allergies", "")
_TRUE_WORDS = ("true", "yes", "y", "1", "witnessed", "on")


class Vocabulary:
    def __init__(self, keys: dict[str, dict], contradiction_keys: set[str], people: Optional[dict] = None,
                 speaker_roles: Optional[dict] = None):
        self.keys = keys
        self.contradiction_keys = contradiction_keys
        self.people = people or {}
        self.speaker_roles = speaker_roles or {}

    @classmethod
    def from_config(cls, rel: str = "vocabulary.yaml") -> "Vocabulary":
        data = load_yaml(rel)
        keys = {k: {**v, **({"range": tuple(v["range"])} if "range" in v else {})} for k, v in data["keys"].items()}
        return cls(keys, set(data["contradiction_keys"]), data.get("people"), data.get("speaker_roles"))

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def meta(self, key: str) -> dict:
        return self.keys[key]

    def label(self, key: str) -> str:
        return self.keys[key]["label"]

    def speaker_role(self, speaker: Optional[str]) -> Optional[str]:
        """The role name for a speaker named on someone else's mic ("neighbor" -> "bystander"), or None if unknown."""
        word = (speaker or "").strip().lower()
        for role, groups in self.speaker_roles.items():
            for g in groups:
                if word == g or word in (self.people.get(g) or []):
                    return role
        return None

    def coerce(self, key: str, value: Any) -> Any:
        """Convert an extracted value to the key's declared type; ValueError if it can't be."""
        meta = self.keys[key]
        if value is None:
            return None
        if meta["type"] == "record":
            return self._record(key, meta, value)
        v = _coerce(meta["type"], value, key)
        if meta.get("enum"):                   # a controlled list: every item must be one of the declared values
            allowed = {x.lower(): x for x in meta["enum"]}
            items = v if isinstance(v, list) else [v]
            bad = [x for x in items if str(x).strip().lower() not in allowed]
            if bad:
                raise ValueError(f"{key}: {bad} not in the allowed values")
            v = [allowed[str(x).strip().lower()] for x in items] if isinstance(v, list) else allowed[str(v).strip().lower()]
        return v

    def _record(self, key: str, meta: dict, value: Any) -> dict:
        """A structured event (e.g. one medication given): declared fields only, each coerced to its own type.
        A bare string is read as the identity field ("aspirin" -> {"drug": "aspirin"})."""
        fields: dict[str, str] = meta["fields"]
        identity = meta["identity"]
        if isinstance(value, str):
            value = {identity: value}
        if not isinstance(value, dict):
            raise ValueError(f"cannot coerce {value!r} to a {key} record")
        # record numbers keep their precision: a dose of 0.15 mg must not become 0.1 (pediatric epinephrine)
        out = {f: _coerce(t, value[f], f"{key}.{f}", digits=4) for f, t in fields.items()
               if value.get(f) not in (None, "", [])}
        if not out.get(identity):
            raise ValueError(f"{key} needs its {identity}")
        for f, groups in (meta.get("field_synonyms") or {}).items():       # e.g. by: "husband" -> "family"
            if isinstance(out.get(f), str):
                word = out[f].strip().lower()
                out[f] = next((canon for canon, words in groups.items() if word == canon or word in words), word)
        return out

    def validate(self, key: str, value: Any) -> Any:
        """Coerce and check physical plausibility (a safety validator). Returns the coerced value."""
        if key not in self.keys:
            raise ValueError(f"unknown key {key}")
        v = self.coerce(key, value)
        meta = self.keys[key]
        checks = [(key, v, meta.get("range"))]
        if isinstance(v, dict):
            checks = [(f"{key}.{f}", v.get(f), tuple(b)) for f, b in (meta.get("field_ranges") or {}).items()]
        for name, x, bounds in checks:
            if bounds and x is not None and not (bounds[0] <= x <= bounds[1]):
                raise ValueError(f"implausible {name} {x!r}: outside {bounds[0]}-{bounds[1]}")
        return v


def _coerce(t: str, value: Any, name: str, digits: int = 1) -> Any:
    try:
        if t == "int":
            return int(round(float(value)))
        if t == "float":
            return round(float(value), digits)
        if t == "bool":
            return value.strip().lower() in _TRUE_WORDS if isinstance(value, str) else bool(value)
        if t == "list":
            if isinstance(value, str):
                return [] if value.strip().lower() in _EMPTY_LIST_WORDS else [value.strip()]
            return [str(x).strip() for x in value]
        return str(value).strip()
    except (TypeError, ValueError):
        raise ValueError(f"cannot coerce {value!r} to {t} for {name}")


def norm_value(v: Any) -> Any:
    """Comparison form of a value: lists as sorted lowercase tuples, strings lowercase, records field by field."""
    if isinstance(v, dict):
        return tuple(sorted((k, norm_value(x)) for k, x in v.items() if x is not None))
    if isinstance(v, list):
        return tuple(sorted(str(x).strip().lower() for x in v))
    if isinstance(v, str):
        return v.strip().lower()
    return v


@lru_cache(maxsize=1)
def default_vocabulary() -> Vocabulary:
    return Vocabulary.from_config()
