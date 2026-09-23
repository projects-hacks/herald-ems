"""The UI contract (GET /api/meta, ui/public/contract/*.json) stays in step with the live modules."""
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["HERALD_WARM_STT"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from herald import app as app_mod  # noqa: E402
from herald import contract, county  # noqa: E402
from herald.checklists import ALERTS  # noqa: E402
from herald.relay import TIERS  # noqa: E402
from herald.schema import KEYS  # noqa: E402
from herald.state import CHANGE_RULE_TEXT, CHANGE_RULES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_every_change_rule_has_text_and_every_tier_key_exists():
    assert set(CHANGE_RULE_TEXT) == set(CHANGE_RULES)
    tier_keys = [k for _, _, ks in TIERS for k in ks]
    assert len(tier_keys) == len(set(tier_keys)), "a key is in two relay tiers"
    for k in tier_keys:
        assert k in KEYS or k.startswith(("score.", "alert.")), k
    for a in ALERTS.values():
        for k, _ in a["items"]:
            assert k in KEYS or k.startswith("@"), k


def test_meta_endpoint_matches_modules():
    meta = TestClient(app_mod.app).get("/api/meta").json()
    assert meta["keys"] == json.loads(json.dumps(KEYS))
    assert meta["relay_tiers"]["code_status"] == {"tier": 1, "why": TIERS[0][1]}
    assert meta["change_rules"] == CHANGE_RULE_TEXT
    assert [i["key"] for i in meta["checklists"]["stroke"]["items"]] == [k for k, _ in county.active()["stroke"]["checklist"]]
    assert [i["key"] for i in meta["checklists"]["stemi"]["items"]] == [k for k, _ in ALERTS["stemi"]["items"]]
    assert meta["county"]["id"] == county.active()["id"] and "santa_clara" in meta["counties"]
    assert "confirmed" in meta["enums"]["status"]


def test_export_script_writes_the_same_data(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_ui_contract.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    for name, build in contract.FILES.items():
        assert json.loads((tmp_path / name).read_text()) == json.loads(json.dumps(build())), name


def test_county_switch_is_live():
    c = TestClient(app_mod.app)
    before = county.active()["id"]
    try:
        assert c.post("/api/county/generic").json()["primary_stroke_scale"] == "RACE"
        assert c.get("/api/meta").json()["checklists"]["stroke"]["items"][2]["key"] == "@race"
        assert c.post("/api/county/santa_clara").json()["primary_stroke_scale"] == "GFAST"
        assert c.get("/api/state").json()["county"]["id"] == "santa_clara"
        assert c.post("/api/county/nowhere").status_code == 404
    finally:
        county.activate(before)


def test_every_county_config_is_valid():
    for cid in county.available():
        cfg = county.load(cid)
        for key, _ in cfg["stroke"]["checklist"]:
            assert key in KEYS or key in county.SCALES.values(), (cid, key)
