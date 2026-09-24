"""Field fact cards (eval/field_cards_v1.jsonl): what a speaker must get across, and the gold facts that speech
should produce. The label is the card, not the speech: speakers use their own words, never a script.

A card line: {"id", "call_type", "dispatch", "by": "medic"|"other", "speaker", "say": [items], "facts":
[[key, value, role]], "note"}. `speaker` is who is talking on the other mic ("wife"); null on the medic's mic."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from herald.core.schema import CapturedBy, Role
from herald.core.vocabulary import Vocabulary, default_vocabulary

ROLES = {Role.medic.value, Role.patient.value, Role.family.value, Role.bystander.value}
SAY_ITEMS = (3, 6)


@dataclass(frozen=True)
class Card:
    id: str
    call_type: str
    dispatch: Optional[str]
    by: CapturedBy
    speaker: Optional[str]
    say: tuple[str, ...]
    facts: tuple[tuple, ...]          # (key, value, role), in the labeling guide's normalized form
    note: str = ""

    def view(self) -> dict:
        """What the recording page shows the speaker: never the labels."""
        return {"id": self.id, "call_type": self.call_type, "dispatch": self.dispatch, "by": self.by.value,
                "speaker": self.speaker, "say": list(self.say)}


def parse_card(d: dict, vocab: Vocabulary) -> Card:
    cid = d.get("id")
    if not cid or not isinstance(cid, str):
        raise ValueError(f"card without an id: {d}")
    try:
        by = CapturedBy(d["by"])
    except (KeyError, ValueError):
        raise ValueError(f"{cid}: by must be medic or other")
    if by not in (CapturedBy.medic, CapturedBy.other):
        raise ValueError(f"{cid}: by must be medic or other")
    speaker = d.get("speaker") or None
    if by == CapturedBy.other and not speaker:
        raise ValueError(f"{cid}: a card on the other mic names who is speaking")
    if by == CapturedBy.medic and speaker:
        raise ValueError(f"{cid}: the medic's mic has no speaker label")
    say = d.get("say") or []
    if not (SAY_ITEMS[0] <= len(say) <= SAY_ITEMS[1]) or not all(isinstance(s, str) and s.strip() for s in say):
        raise ValueError(f"{cid}: say needs {SAY_ITEMS[0]}-{SAY_ITEMS[1]} non-empty items")
    facts = []
    for f in d.get("facts") or []:
        if not isinstance(f, list) or len(f) != 3:
            raise ValueError(f"{cid}: a fact is [key, value, role], got {f}")
        key, value, role = f
        try:
            vocab.validate(key, value)
        except ValueError as e:
            raise ValueError(f"{cid}: {e}")
        if role not in ROLES:
            raise ValueError(f"{cid}: role {role!r} is not one of {sorted(ROLES)}")
        facts.append((key, value, role))
    if not facts:
        raise ValueError(f"{cid}: no facts")
    return Card(cid, str(d.get("call_type") or ""), d.get("dispatch") or None, by, speaker, tuple(say),
                tuple(facts), str(d.get("note") or ""))


def load_cards(path: Path, vocab: Optional[Vocabulary] = None) -> dict[str, Card]:
    """Every card, validated against the vocabulary (keys, types, enums, plausibility); ids are unique."""
    vocab = vocab or default_vocabulary()
    cards: dict[str, Card] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        card = parse_card(json.loads(line), vocab)
        if card.id in cards:
            raise ValueError(f"duplicate card id {card.id}")
        cards[card.id] = card
    return cards


def assign(card_ids: list[str], speaker_index: int, per_speaker: int) -> list[str]:
    """The cards speaker number `speaker_index` (0-based) says: consecutive blocks that wrap around, so every card
    is said before any card is said twice."""
    n = len(card_ids)
    return [card_ids[(speaker_index * per_speaker + i) % n] for i in range(min(per_speaker, n))]


def condition_order(conditions: list[str], speaker_index: int) -> list[str]:
    """Counterbalanced: odd-numbered speakers start with the second condition, so practice doesn't favor one."""
    k = speaker_index % len(conditions)
    return conditions[k:] + conditions[:k]
