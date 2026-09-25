"""The registry of device-layout families: which renderer, which capture mode, how often, and which layout
variants are held out for dev. A family's held-out variants never appear in train, so dev measures reading an
unseen layout of a known device type. Adding a layout = adding a variant to a renderer and its number here."""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Callable

from . import render_documents as docs
from . import render_handheld as hand
from . import render_labels as labels
from . import render_monitors as mon
from . import render_negatives as neg
from . import render_polst as polst
from . import render_wearables as wear
from .spec import Panel


@dataclass(frozen=True)
class Family:
    name: str
    mode: str
    render: Callable
    variants: int
    dev: frozenset           # held-out variant numbers
    weight: float
    needs_catalog: bool = False

    def train_variants(self) -> list[int]:
        return [v for v in range(self.variants) if v not in self.dev]


FAMILIES = [
    Family("bedside_monitor", "monitor", mon.bedside, 5, frozenset({4}), 0.10),
    Family("defib_monitor", "monitor", mon.defib, 3, frozenset({2}), 0.05),
    Family("aed", "monitor", mon.aed, 3, frozenset({2}), 0.025),
    Family("capnograph", "monitor", mon.capnograph, 2, frozenset({1}), 0.02),
    Family("fingertip_oximeter", "monitor", hand.oximeter, 4, frozenset({3}), 0.08),
    Family("bp_cuff", "monitor", hand.bp_cuff, 4, frozenset({3}), 0.07),
    Family("glucometer", "monitor", hand.glucometer, 4, frozenset({3}), 0.06),
    Family("thermometer", "monitor", hand.thermometer, 4, frozenset({3}), 0.05),
    Family("smartwatch", "monitor", wear.smartwatch, 5, frozenset({4}), 0.07),
    Family("fitness_band", "monitor", wear.band, 3, frozenset({2}), 0.03),
    Family("phone_app", "monitor", wear.phone_app, 4, frozenset({3}), 0.06),
    Family("household_display", "monitor", neg.household_display, 6, frozenset({5}), 0.035),
    Family("pharmacy_label", "pill_bottle", labels.pharmacy_label, 4, frozenset({3}), 0.09, True),
    Family("stock_package", "pill_bottle", labels.stock_package, 3, frozenset({2}), 0.04, True),
    Family("device_label", "pill_bottle", labels.device_label, 3, frozenset({2}), 0.03, True),
    Family("med_list", "pill_bottle", labels.med_list, 3, frozenset({2}), 0.04, True),
    Family("product_label", "pill_bottle", neg.product_label, 3, frozenset({2}), 0.015),
    Family("order_form", "form", docs.order_form, 4, frozenset({3}), 0.09),
    Family("non_order_document", "form", docs.non_order_document, 5, frozenset({4}), 0.035),
    # the real CA POLST page, filled by hand; weight 0: added by make_polst.py, not by the proportional plan
    Family("ca_polst", "form", polst.ca_polst, 4, frozenset({3}), 0.0),
]
BY_NAME = {f.name: f for f in FAMILIES}
TORN_LABEL_RATE = 0.04      # label-mode photos where one printed drug line is torn or smudged away


def plan(n: int, dev_frac: float) -> list[tuple[str, int, str]]:
    """(split, index, family) for every example, proportional to the weights (largest-remainder rounding)."""
    out = []
    total = sum(f.weight for f in FAMILIES)
    for split, count in (("train", n - round(n * dev_frac)), ("dev", round(n * dev_frac))):
        raw = [(f, count * f.weight / total) for f in FAMILIES]
        alloc = {f.name: int(x) for f, x in raw}
        rest = count - sum(alloc.values())
        for f, x in sorted(raw, key=lambda t: t[1] - int(t[1]), reverse=True)[:rest]:
            alloc[f.name] += 1
        i = 0
        for f in FAMILIES:
            for _ in range(alloc[f.name]):
                out.append((split, i, f.name))
                i += 1
    return out


def tear(panel: Panel, rng: Random) -> None:
    """Tear or smudge away one drug line on a label (the reading becomes unreadable: the prompt says omit it)."""
    from PIL import ImageDraw
    meds = [r for r in panel.readings if r.key == "meds.list" and r.readable and r.box]
    if not meds:
        return
    r = rng.choice(meds)
    x0, y0, x1, y1 = r.box
    d = ImageDraw.Draw(panel.image)
    pad = 6
    pts = [(x0 - pad + rng.uniform(-8, 8), y0 - pad + rng.uniform(-6, 6)) for _ in range(1)]
    xs = [x0 - pad + (x1 - x0 + 2 * pad) * t / 10 for t in range(11)]
    top = [(x, y0 - pad - rng.uniform(0, 10)) for x in xs]
    bot = [(x, y1 + pad + rng.uniform(0, 10)) for x in reversed(xs)]
    style = rng.choice(["torn", "smudge", "marker"])
    color = {"torn": (235, 225, 205, 255), "smudge": (120, 110, 100, 255), "marker": (15, 15, 15, 255)}[style]
    d.polygon(pts + top + bot, fill=color)
    r.readable, r.why_unreadable = False, style
    r.strength_readable = False


def render(name: str, rng: Random, variant: int, catalog=None) -> Panel:
    fam = BY_NAME[name]
    panel = fam.render(rng, variant, catalog) if fam.needs_catalog else fam.render(rng, variant)
    if fam.mode == "pill_bottle" and rng.random() < TORN_LABEL_RATE:
        tear(panel, rng)
    return panel
