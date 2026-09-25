"""Write the UI contract files the React build ships with (ui/public/contract/*.json).

Run from the repo root:  python scripts/export_ui_contract.py [--out ui/public/contract]
The same data is live at GET /api/meta. Re-run after changing config/vocabulary.yaml, config/relay.yaml,
config/trends.yaml, config/checklists.yaml, config/scores/*.yaml or a county's checklists (config/counties/*.json);
Run this after changing the vocabulary, scores or relay configuration. Files: keys.json, relay_tiers.json, change_rules.json,
checklists.json (the default county's), scores.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from herald.api import build_context  # noqa: E402
from herald.config import Settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "ui" / "public" / "contract"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    settings = Settings.from_env({}).model_copy(update={"knowledge": False, "terminology": False, "warm_stt": False})
    ctx = build_context(settings)  # content only: no weights, embedding index, or model requests
    for name, content in ctx.contract.files().items():
        (out / name).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out / name}")


if __name__ == "__main__":
    main()
