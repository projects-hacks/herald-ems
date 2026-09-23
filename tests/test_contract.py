"""The UI contract (GET /api/meta, ui/public/contract/*.json) stays in step with the loaded content."""
import json
import subprocess
import sys
from pathlib import Path

from fakes import make_client
from herald.config import CONFIG_DIR, load_yaml
from herald.config.county import SCALE_ITEMS, CountyRegistry
from herald.core.vocabulary import default_vocabulary

ROOT = Path(__file__).resolve().parent.parent


def test_every_trend_rule_has_text_and_every_tier_key_exists():
    vocab = default_vocabulary()
    rules = load_yaml("trends.yaml")["change_rules"]
    assert all(r.get("text") for r in rules.values()) and all(k in vocab for k in rules)
    tier_keys = [k for t in load_yaml("relay.yaml")["tiers"] for k in t["keys"]]
    assert len(tier_keys) == len(set(tier_keys)), "a key is in two relay tiers"
    for k in tier_keys:
        assert k in vocab or k.startswith(("score.", "alert.")), k
    for a in load_yaml("checklists.yaml")["alerts"].values():
        for k, _ in a["items"]:
            assert k in vocab or k.startswith("@"), k


def test_meta_endpoint_matches_the_loaded_content():
    c, ctx = make_client()
    meta = c.get("/api/meta").json()
    assert set(meta["keys"]) == set(default_vocabulary().keys)
    assert meta["relay_tiers"]["code_status"]["tier"] == 1
    assert meta["change_rules"]["vitals.spo2"].startswith("SpO2 fell")
    assert [i["key"] for i in meta["checklists"]["stroke"]["items"]] == [k for k, _ in ctx.counties.active["stroke"]["checklist"]]
    assert [i["key"] for i in meta["checklists"]["stemi"]["items"]] == [k for k, _ in load_yaml("checklists.yaml")["alerts"]["stemi"]["items"]]
    assert meta["county"]["id"] == ctx.counties.active["id"] and "santa_clara" in meta["counties"]
    assert "confirmed" in meta["enums"]["status"]


def test_export_script_writes_the_same_data(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_ui_contract.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    _, ctx = make_client()
    for name, content in ctx.contract.files().items():
        assert json.loads((tmp_path / name).read_text()) == json.loads(json.dumps(content)), name


def test_county_switch_is_live():
    c, _ = make_client()
    assert c.post("/api/county/generic").json()["primary_stroke_scale"] == "RACE"
    assert c.get("/api/meta").json()["checklists"]["stroke"]["items"][2]["key"] == "@race"
    assert c.post("/api/county/santa_clara").json()["primary_stroke_scale"] == "GFAST"
    assert c.get("/api/state").json()["county"]["id"] == "santa_clara"
    assert c.post("/api/county/nowhere").status_code == 404


def test_every_county_config_is_valid():
    vocab = default_vocabulary()
    reg = CountyRegistry("santa_clara")
    for cid in reg.available():
        cfg = reg.load(cid)
        for key, _ in cfg["stroke"]["checklist"]:
            assert key in vocab or key in SCALE_ITEMS.values(), (cid, key)


def test_no_clinical_numbers_left_in_python():
    """Rule 4: score tables and thresholds live in config/, not in the engines."""
    for path in (ROOT / "herald" / "scoring").glob("*.py"):
        text = path.read_text()
        for needle in ("Royal College", "Pérez de la Ossa", "185,835", "0.85, specificity"):
            assert needle not in text, (path.name, needle)
    assert (CONFIG_DIR / "scores" / "news2.yaml").exists()
