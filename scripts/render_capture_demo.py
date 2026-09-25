"""Render synthetic rehearsal props on the CPU, reusing the photo evaluation renderers."""
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.photos.render.displays import bedside_monitor
from eval.photos.render.documents import polst
from eval.photos.render.primitives import text


def vial(spec, cfg, rng):
    image = Image.new("RGB", (900, 900), (90, 100, 110))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((140, 50, 760, 850), radius=60, fill=(220, 225, 220), outline=(20, 25, 30), width=6)
    draw.rectangle((180, 220, 720, 780), fill=(248, 248, 240))
    for i, line in enumerate(spec["lines"]):
        text(draw, (450, 260 + i * 90), line, "sans_bold", 28 if i == 0 else 36, (20, 25, 30), anchor="ma")
    return image, {}


def main():
    folder = ROOT / "scenarios/frames/auto_capture"
    specs = json.loads((folder / "specs.json").read_text())
    cfg = yaml.safe_load((ROOT / "eval/photos/specs.yaml").read_text())
    renderers = {"monitor": bedside_monitor, "polst": polst, "vial": vial}
    for spec in specs["frames"]:
        image, _ = renderers[spec["kind"]](spec, cfg, random.Random(0))
        image = image.convert("RGB")
        image.thumbnail((1280, 1280))
        image.save(folder / f"{spec['id']}.jpg", quality=90)
        print(spec["id"], image.size)


if __name__ == "__main__":
    main()
