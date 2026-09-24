"""One checklist item and how it is satisfied.

An item's `key` (as written in config) is one of:
  - a vocabulary key                      `vitals.sbp`                 done when the key has a confirmed value
  - a score                               `@trauma_605`                done when the score is complete or met
  - a record field                        `meds.given[drug=aspirin]`   done when a confirmed record has that field value
  - alternatives, any of the above        `vitals.consciousness|vitals.gcs_total`
An item may carry `note` (shown while it is not done, e.g. "not measured"), `source` (its citation), and `when`
(a criteria rule from herald/scoring/rules.py; the item is listed unless the rule is decided false).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Union

from ..scoring.rules import evaluate

_RECORD = re.compile(r"^(?P<key>[\w.]+)\[(?P<field>\w+)=(?P<value>[^\]]+)\]$")


@dataclass(frozen=True)
class Ref:
    """One alternative of an item key."""
    kind: str                     # key | score | record
    key: str                      # the vocabulary key, or the score id
    field: Optional[str] = None
    value: Optional[str] = None

    @classmethod
    def parse(cls, text: str) -> "Ref":
        text = text.strip()
        if text.startswith("@"):
            return cls("score", text[1:])
        m = _RECORD.match(text)
        if m:
            return cls("record", m["key"], m["field"], m["value"].strip())
        return cls("key", text)

    def satisfied(self, values: dict[str, Any], scores: dict[str, dict]) -> bool:
        if self.kind == "score":
            r = scores.get(self.key) or {}
            return bool(r.get("complete") or r.get("met") is True)
        if self.kind == "record":
            want = self.value.lower()
            return any(isinstance(r, dict) and str(r.get(self.field, "")).strip().lower() == want
                       for r in values.get(self.key) or [])
        return self.key in values


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    label: str
    note: Optional[str] = None
    source: Optional[str] = None
    when: Optional[dict] = None

    @classmethod
    def parse(cls, row: Union[list, tuple, dict]) -> "ChecklistItem":
        if isinstance(row, dict):
            return cls(row["key"], row["label"], row.get("note"), row.get("source"), row.get("when"))
        key, label = row
        return cls(key, label)

    @property
    def refs(self) -> list[Ref]:
        return [Ref.parse(x) for x in self.key.split("|")]

    @property
    def vocab_keys(self) -> list[str]:
        """The vocabulary keys this item reads (empty for a score item)."""
        return [r.key for r in self.refs if r.kind != "score"]

    def listed(self, values: dict[str, Any]) -> bool:
        return self.when is None or evaluate(self.when, values).met is not False

    def state(self, confirmed: dict, everything: dict, scores: dict, scores_all: dict, started: set[str]) -> str:
        """done (confirmed facts satisfy it), pending (it would be done once waiting facts are confirmed, or its
        stroke exam has started), or missing."""
        refs = self.refs
        if any(r.satisfied(confirmed, scores) for r in refs):
            return "done"
        if any(r.satisfied(everything, scores_all) or (r.kind == "score" and r.key in started) for r in refs):
            return "pending"
        return "missing"
