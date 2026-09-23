"""The UI contract: labels, units, relay tiers, change rules, and checklists, as plain data.

The snapshot carries values; the screens need to name them, including keys that are no longer in the
snapshot (a relay log line, a closed gap). Served at GET /api/meta and exported to ui/public/contract/
by scripts/export_ui_contract.py. tests/test_contract.py keeps the two in step with these modules.
"""
from __future__ import annotations

from .checklists import ALERTS, DEFAULT_UNKNOWNS
from .relay import BUDGET, TIERS
from .schema import CONTRADICTION_KEYS, KEYS, CapturedBy, Role, Status
from .state import CHANGE_RULE_TEXT


def keys() -> dict:
    return {k: dict(v) for k, v in KEYS.items()}


def relay_tiers() -> dict:
    return {k: {"tier": p, "why": why} for p, why, ks in TIERS for k in ks}


def change_rules() -> dict:
    return dict(CHANGE_RULE_TEXT)


def checklists() -> dict:
    return {name: {"label": a["label"], "items": [{"key": k, "label": lbl} for k, lbl in a["items"]],
                   "unknowns": list(a["unknowns"])}
            for name, a in ALERTS.items()} | {"_default_unknowns": list(DEFAULT_UNKNOWNS)}


def ui_contract() -> dict:
    return {
        "keys": keys(),
        "relay_tiers": relay_tiers(),
        "relay_budget_bytes": dict(BUDGET),
        "change_rules": change_rules(),
        "checklists": checklists(),
        "contradiction_keys": sorted(CONTRADICTION_KEYS),
        "enums": {"role": [r.value for r in Role], "captured_by": [c.value for c in CapturedBy],
                  "status": [s.value for s in Status]},
    }


# file name under ui/public/contract/ -> builder
FILES = {"keys.json": keys, "relay_tiers.json": relay_tiers, "change_rules.json": change_rules,
         "checklists.json": checklists}
