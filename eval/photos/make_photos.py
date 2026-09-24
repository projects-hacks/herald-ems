#!/usr/bin/env python3
"""Render the synthetic photo test set and its gold labels, reproducibly.

  python eval/photos/make_photos.py                 # writes eval/photos/<id>.jpg and eval/photos/gold.jsonl
  python eval/photos/make_photos.py --sheet /tmp/x  # also writes a contact sheet for eyeballing the set

What each image shows is data (eval/photos/specs.yaml); this script is the engine. Gold facts are derived from the
rendering parameters only, never from a model. Every item gets its own random stream seeded from (seed, id), so
adding an item never changes the others.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import yaml
from PIL import Image

HERE = Path(__file__).resolve().parent
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(HERE.parent.parent))
from eval.photos.render import RENDERERS, degrade, place  # noqa: E402

MAX_SIDE = 1024


# ---------- gold labels from rendering parameters ----------
def hidden_keys(spec: dict, fields: dict) -> set[str]:
    """Fields covered by an occlusion step. Keys drawn in the same box (SBP/DBP) are hidden together."""
    hidden = set()
    for step in spec.get("degrade", []):
        if step["kind"] == "occlusion":
            box = fields[step["field"]]
            hidden |= {k for k, b in fields.items() if b == box}
    return hidden


def value_facts(spec: dict, hidden: set[str]) -> list[list]:
    return [[k, v] for k, v in spec.get("values", {}).items() if k not in hidden]


def med_facts(spec: dict) -> tuple[list[list], dict]:
    """meds.list = [generic]; meds.anticoagulant = generic when the spec says so. Printed names are aliases."""
    facts = [["meds.list", [spec["generic"]]]]
    if spec.get("anticoagulant"):
        facts.append(["meds.anticoagulant", spec["anticoagulant"]])
    printed = [spec.get(k) for k in ("printed_name", "printed_generic", "generic_for")]
    aliases = sorted({p.lower() for p in printed if p and p.lower() != spec["generic"]})
    return facts, ({"meds.list": aliases} if aliases else {})


def form_facts(spec: dict, cfg: dict) -> tuple[list[list], dict]:
    """code_status from the checked resuscitation option; its printed text is an accepted alias."""
    chosen = spec.get("section_a")
    if not chosen:
        return [], {}
    opt = cfg["forms"]["polst"]["section_a"]["options"][chosen]
    return [["code_status", opt["canonical"]]], {"code_status": [opt["text"]]}


def gold_line(spec: dict, cfg: dict, fields: dict) -> dict:
    aliases: dict = {}
    if spec["device"] in ("pill_label", "otc_bottle"):
        facts, aliases = med_facts(spec)
    elif spec["device"] == "polst":
        facts, aliases = form_facts(spec, cfg)
    else:
        facts = value_facts(spec, hidden_keys(spec, fields))
    line = {"file": f"{spec['id']}.jpg", "mode": spec["mode"], "facts": facts,
            "degradations": sorted({s["kind"] for s in spec.get("degrade", [])}),
            "device": spec["device"], "notes": spec.get("notes", "")}
    if aliases:
        line["aliases"] = aliases
    if spec.get("strength") and spec["device"] in ("pill_label", "otc_bottle"):
        line["strength"] = spec["strength"]
    hidden = hidden_keys(spec, fields) & set(spec.get("values", {}))
    if hidden:
        line["notes"] = (line["notes"] + f" Occluded (not in gold): {sorted(hidden)}.").strip()
    return line


# ---------- rendering ----------
def render_item(spec: dict, cfg: dict) -> tuple[Image.Image, dict]:
    rng = random.Random(f"{cfg['seed']}:{spec['id']}")
    device, fields = RENDERERS[spec["device"]](spec, cfg, rng)
    canvas = tuple(cfg["canvas"])
    if device.height > device.width:                 # paper held upright: shoot in portrait
        canvas = canvas[::-1]
    photo, fields = place(device, fields, canvas, rng)
    photo = degrade(photo, spec.get("degrade", []), fields, rng)
    if max(photo.size) > MAX_SIDE:
        s = MAX_SIDE / max(photo.size)
        photo = photo.resize((round(photo.width * s), round(photo.height * s)), Image.LANCZOS)
    return photo, fields


def existing_lines(cfg: dict) -> list[dict]:
    out = []
    for e in cfg.get("existing", []):
        line = {"file": e["file"], "mode": e["mode"], "facts": e["facts"], "degradations": e.get("degradations", []),
                "device": "existing", "notes": e.get("notes", "")}
        if e.get("aliases"):
            line["aliases"] = e["aliases"]
        if e.get("strength"):
            line["strength"] = e["strength"]
        out.append(line)
    return out


def contact_sheet(files: list[Path], out: Path, cols: int = 6, cell: int = 300) -> None:
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (255, 255, 255))
    for i, f in enumerate(files):
        im = Image.open(f)
        im.thumbnail((cell - 6, cell - 6))
        sheet.paste(im, ((i % cols) * cell + 3, (i // cols) * cell + 3))
    sheet.save(out, quality=85)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specs", default=str(HERE / "specs.yaml"))
    ap.add_argument("--out-dir", default=str(HERE))
    ap.add_argument("--sheet", default=None, help="also write a contact sheet (JPEG) to this path")
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.specs).read_text())
    out_dir = Path(a.out_dir)
    lines, files = existing_lines(cfg), []
    for spec in cfg["items"]:
        photo, fields = render_item(spec, cfg)
        path = out_dir / f"{spec['id']}.jpg"
        photo.save(path, "JPEG", quality=cfg.get("jpeg_quality", 90))
        files.append(path)
        lines.append(gold_line(spec, cfg, fields))
    with open(out_dir / "gold.jsonl", "w") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")
    if a.sheet:
        contact_sheet(files, Path(a.sheet))
    print(f"wrote {len(files)} images and {len(lines)} gold lines to {out_dir}")


if __name__ == "__main__":
    main()
