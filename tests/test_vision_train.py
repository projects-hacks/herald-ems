"""The vision training-photo generator (scripts/vision_train/, docs/MODEL_PLAN.md §2a "Vision training set"):
targets are exactly what the product's photo reader accepts, the generator is deterministic per seed, dev layouts
never appear in train, and nothing is taken from the test photos. CPU only; label families need the RxNorm index
and are skipped without it."""
import json
from pathlib import Path
from random import Random

import pytest

from herald.config import get_settings, load_yaml
from herald.core.vocabulary import default_vocabulary
from scripts.vision_train import families, targets
from scripts.vision_train.decontam import Exclusions, phash, value_set
from scripts.vision_train.photo import photograph
from scripts.vision_train.spec import Reading
from scripts.vision_train.validate import ReaderCheck

ROOT = Path(__file__).resolve().parent.parent
INDEX = get_settings().terminology_index
BUILT = ROOT / "data/vision_train"
needs_index = pytest.mark.skipif(not INDEX.exists(), reason="RxNorm index not built (scripts/build_rxnorm_index.py)")
PROMPTS = targets.Prompts.load()


@pytest.fixture(scope="module")
def catalog():
    if not INDEX.exists():
        return None
    from scripts.vision_train.drugs import build_catalog, load_normalizer
    cat = build_catalog(INDEX, load_normalizer(INDEX))
    cat.exclude(Exclusions().drug_strengths)
    return cat


def _example(name: str, seed: str, variant: int, catalog):
    rng = Random(seed)
    panel = families.render(name, rng, variant, catalog)
    ex = photograph(panel, rng, "t", hard=rng.uniform(0, 1))
    return panel, ex, targets.build(panel.mode, panel.readings, ex.severity, PROMPTS)


def _families(catalog):
    return [f for f in families.FAMILIES if catalog is not None or not f.needs_catalog]


# ---------- targets are what the product accepts ----------
def test_every_family_mode_is_a_production_mode():
    for f in families.FAMILIES:
        assert f.mode in PROMPTS.modes, f.name


def test_prompts_come_from_config_not_a_copy():
    cfg = load_yaml("prompts/vision.yaml")
    assert PROMPTS.system == cfg["system"] and PROMPTS.modes == cfg["modes"]


def test_generated_targets_survive_the_reader_and_the_vocabulary(catalog):
    check = ReaderCheck(INDEX if INDEX.exists() else None)
    vocab = default_vocabulary()
    for f in _families(catalog):
        for v in range(f.variants):
            panel, ex, t = _example(f.name, f"test:{f.name}:{v}", v, catalog)
            assert check.problems(panel.mode, t) == [], (f.name, v, t)
            for fact in t["facts"]:
                assert fact["key"] in vocab and fact["key"] in PROMPTS.scope(panel.mode)
                assert list(fact)[:2] == ["key", "value"] and 0 <= fact["confidence"] <= 1
                assert all(0 <= x <= 1 for x in fact["box"]) and fact["box"][0] <= fact["box"][2]
            assert max(ex.image.size) <= 1024 and ex.jpeg[:2] == b"\xff\xd8"


def test_unreadable_and_out_of_scope_readings_are_omitted():
    rs = [Reading("vitals.hr", 88, (0.1, 0.1, 0.2, 0.2)), Reading("vitals.spo2", 91, (0.1, 0.3, 0.2, 0.4), readable=False),
          Reading("vitals.etco2", 38, (0.1, 0.5, 0.2, 0.6))]
    keys = [f["key"] for f in targets.build("monitor", rs, 0.0, PROMPTS)["facts"]]
    assert "vitals.spo2" not in keys and "vitals.hr" in keys
    assert ("vitals.etco2" in keys) == ("vitals.etco2" in PROMPTS.scope("monitor"))   # follows the prompt


def test_units_convert_to_what_the_prompt_asks():
    from scripts.vision_train.values import glucose_display, temp_display
    rng = Random(1)
    shown, c = temp_display(rng, 38.5, fahrenheit=True)
    assert abs((float(shown) - 32) * 5 / 9 - c) < 0.051
    shown, mgdl = glucose_display(rng, 144, mmol=True)
    assert shown == "8.0" and mgdl == 144


def test_label_target_is_generic_with_strength_and_a_brand_label_still_gives_generic(catalog):
    if catalog is None:
        pytest.skip("RxNorm index not built")
    seen_brand = False
    for k in range(40):
        panel, _, t = _example("pharmacy_label", f"brand:{k}", 0, catalog)
        for r in panel.readings:
            if r.readable:
                fact = next(f for f in t["facts"] if f["value"] == [r.value])
                assert fact["value"][0] == fact["value"][0].lower()
                assert fact.get("strength") == (r.strength if r.strength_readable else None)
                seen_brand |= r.value not in r.shown.lower()
    assert seen_brand


# ---------- determinism ----------
@pytest.mark.parametrize("name", ["bedside_monitor", "bp_cuff", "phone_app", "order_form", "household_display"])
def test_generator_is_deterministic_per_seed(name):
    a = _example(name, "seed-a", 0, None)
    b = _example(name, "seed-a", 0, None)
    c = _example(name, "seed-b", 0, None)
    assert a[1].jpeg == b[1].jpeg and a[2] == b[2]
    assert a[1].jpeg != c[1].jpeg


@needs_index
def test_label_generator_is_deterministic_per_seed(catalog):
    a, b = _example("med_list", "s", 1, catalog), _example("med_list", "s", 1, catalog)
    assert a[1].jpeg == b[1].jpeg and a[2] == b[2]


# ---------- held-out design ----------
def test_dev_layouts_are_disjoint_from_train_in_the_registry():
    for f in families.FAMILIES:
        assert f.dev and f.train_variants(), f.name
        assert not set(f.dev) & set(f.train_variants())


def test_plan_holds_out_about_eight_percent_across_every_family():
    jobs = families.plan(1000, 0.08)
    dev = [j for j in jobs if j[0] == "dev"]
    assert len(jobs) == 1000 and len(dev) == 80
    assert {j[2] for j in dev} == {f.name for f in families.FAMILIES if f.weight > 0}   # weight-0 families (ca_polst) have their own builder


@pytest.mark.skipif(not (BUILT / "dev.jsonl").exists(), reason="training set not built")
def test_built_set_dev_layouts_unseen_in_train_and_prompts_current():
    rows = {s: [json.loads(x) for x in open(BUILT / f"{s}.jsonl")] for s in ("train", "dev")}
    assert not {r["layout"] for r in rows["train"]} & {r["layout"] for r in rows["dev"]}
    assert not {r["seed"] for r in rows["train"]} & {r["seed"] for r in rows["dev"]}
    stale = [r["id"] for s in rows.values() for r in s
             if r["system"] != PROMPTS.system or r["user"] != PROMPTS.modes[r["mode"]]]
    assert not stale, f"{len(stale)} rows carry an old prompt: run scripts/vision_train/make.py --retarget"


@pytest.mark.skipif(not (BUILT / "dev.jsonl").exists(), reason="training set not built")
def test_built_targets_rebuild_from_their_truth():
    for r in [json.loads(x) for x in open(BUILT / "dev.jsonl")][:60]:
        readings = [Reading(**{k: (tuple(v) if isinstance(v, list) and k.endswith("box") else v)
                               for k, v in t.items()}) for t in r["truth"]]
        assert targets.dumps(targets.build(r["mode"], readings, r["severity"], PROMPTS)) == r["target"]


# ---------- decontamination ----------
def test_generator_avoids_test_value_sets_and_labels(catalog):
    ex = Exclusions()
    gold = [r for r in ex.rows if r["mode"] == "monitor" and r["facts"]]
    if gold:
        r = gold[0]
        assert ex.monitor_collides(r["device"], [tuple(f) for f in r["facts"]])
    if catalog is not None:
        for g, s in ex.drug_strengths:
            for p in catalog.by_ing.get(g, []):
                assert p.strength.replace(" ", "").lower() != s.replace(" ", "").lower() or not catalog._allowed(p)


def test_value_set_and_phash_helpers():
    from PIL import Image
    assert value_set([("vitals.hr", 72), ("vitals.spo2", 97)]) == value_set([("vitals.spo2", 97.0), ("vitals.hr", 72)])
    a = Image.new("RGB", (64, 64), (10, 10, 10))
    assert phash(a) == phash(a.resize((128, 128)))


def test_generator_never_reads_test_layouts():
    src = "".join(p.read_text() for p in (ROOT / "scripts/vision_train").glob("*.py") if p.name != "decontam.py")
    for pattern in ('"eval/photos', "'eval/photos", "from eval", "import eval", "make_photos"):
        assert pattern not in src, pattern


# ---------- negatives and no-number screens ----------
@pytest.mark.parametrize("name", ["household_display", "product_label", "non_order_document"])
def test_negative_families_always_answer_no_facts(name):
    f = families.BY_NAME[name]
    for k in range(3 * f.variants):
        _, _, t = _example(name, f"neg:{k}", k % f.variants, None)
        assert t == {"facts": []}, (name, k, t)


def test_hi_lo_error_and_average_screens_carry_no_reading():
    seen = 0
    for name in ("glucometer", "thermometer", "bp_cuff"):
        f = families.BY_NAME[name]
        for k in range(150):
            panel = families.render(name, Random(f"err:{name}:{k}"), k % f.variants, None)
            if panel.notes:              # HI / LO / Err / memory average: nothing current to read
                seen += 1
                assert not panel.readings, (name, k, panel.notes)
    assert seen >= 5


@needs_index
def test_a_torn_drug_line_leaves_the_target(catalog):
    from scripts.vision_train.families import tear
    for k in range(10):
        panel = families.render("pharmacy_label", Random(f"tear:{k}"), 0, catalog)
        tear(panel, Random(k))
        t = targets.build(panel.mode, panel.readings, 0.0, PROMPTS)
        assert t == {"facts": []}
