"""Write the UI contract files the React build ships with (ui/public/contract/*.json).

Run from the repo root:  python scripts/export_ui_contract.py [--out ui/public/contract]
The same data is live at GET /api/meta. Re-run after changing schema.KEYS, relay.TIERS,
state.CHANGE_RULE_TEXT, or checklists.ALERTS (scripts/build_ui.sh does this on every build).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from herald import contract  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "ui" / "public" / "contract"))
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    for name, build in contract.FILES.items():
        (out / name).write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out / name}")


if __name__ == "__main__":
    main()
