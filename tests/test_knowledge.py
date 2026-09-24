"""Protocol lookup (P9) against the archived county documents and the answer keys in eval/protocols/."""
import copy
import json
import shutil
from pathlib import Path

import httpx
import pytest

from fakes import make_client
from herald.knowledge import KnowledgeBase, ProtocolSync
from herald.knowledge.tables import read_check_table

ROOT = Path(__file__).resolve().parent.parent
COUNTY = json.loads((ROOT / "config/counties/santa_clara.json").read_text())
ARCHIVE = ROOT / "data/protocols/santa_clara/archive"
KEYS = ROOT / "eval/protocols"


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase(COUNTY, ROOT / "data/protocols")


def test_every_numbered_section_in_the_key_is_found(kb):
    names = {Path(d["file"]).name: d["id"] for d in COUNTY["documents"]}
    got = {(s.doc_id, s.number) for s in kb.sections}
    key = [json.loads(line) for line in open(KEYS / "sections_key.jsonl")]
    want = {(names[k["doc"]], k["number"]) for k in key if k.get("kind") == "section" and k["number"]
            and (names[k["doc"]] != "602" or 12 <= k["page"] <= 21)}
    assert want <= got, sorted(want - got)[:10]


def test_table_b_matches_the_168_cell_key():
    grid = read_check_table(ARCHIVE / "AO-2025-005_policy-602-destination_eff-2025-04-01.pdf", 20, "R")
    mine = {r["label"]: set(r["checked"]) for r in grid["rows"]}
    key = json.loads((KEYS / "table_b_key.json").read_text())
    for row in key["rows"]:
        for service, checked in row["checks"].items():
            assert (row["abbrev"] in mine[service.lstrip("*")]) == checked, (row["abbrev"], service)


def test_reviewed_destinations_match_policy_602(kb):
    audit = kb.audit_destinations()
    assert {a["service"] for a in audit} == {"Comprehensive Stroke Center", "Primary Stroke Center"}
    assert all(a["match"] for a in audit)


def test_search_cites_the_county_text(kb):
    r = kb.search("Stroke Alert Patient Time Last Known Well within twenty-four hours", 3)[0]
    assert (r["doc"], r["section"], r["page"]) == ("700-A13", "3.1", 1)
    assert r["effective"] == "January 1, 2026" and "twenty-four (24) hours" in r["text"]


def _county_with_mirror(tmp_path):
    county = copy.deepcopy(COUNTY)
    county["documents"] = [d for d in county["documents"] if d["id"] == "700-A13"]
    county["documents"][0]["mirror_url"] = "http://mirror.test/700-A13.pdf"
    (tmp_path / "santa_clara" / "archive").mkdir(parents=True)
    shutil.copy(ARCHIVE / "700-A13_stroke_eff-2026-01-01.pdf", tmp_path / "santa_clara" / "archive")
    return county


def test_sync_stores_a_new_version_flags_review_and_never_edits_config(tmp_path):
    county = _county_with_mirror(tmp_path)
    before = json.dumps(county, sort_keys=True)
    kb = KnowledgeBase(county, tmp_path)
    newer = (ARCHIVE / "501_hospital-radio-reports_eff-2025-01-01.pdf").read_bytes()   # any different PDF
    calls = []

    def fetch(url, headers):
        calls.append(headers)
        if headers.get("If-None-Match") == '"v2"':
            return httpx.Response(304)
        return httpx.Response(200, content=newer, headers={"etag": '"v2"'})

    sync = ProtocolSync(lambda: kb, lambda: "weak", {"sync": {"interval_s": 0, "only_when_link": "good", "timeout_s": 5}},
                        fetch=fetch)
    assert sync.run() is None                         # weak link: no sync
    assert sync.run(force=True)["updated"] == ["700-A13"]
    assert kb.summary()["review_required"] == ["700-A13"]
    assert kb.versions["700-A13"]["file"].startswith("versions/")
    assert sync.run(force=True)["updated"] == [] and calls[-1] == {"If-None-Match": '"v2"'}
    ProtocolSync.mark_reviewed(kb, "700-A13")
    assert kb.summary()["review_required"] == []
    assert json.dumps(county, sort_keys=True) == before   # the reviewed county config is never rewritten


def test_protocol_endpoints():
    c, ctx = make_client(knowledge=True)
    ctx.knowledge.embedder = None
    ctx.knowledge.build()
    st = c.get("/api/protocols").json()
    assert st["ready"] and st["sections"] > 300 and all(a["match"] for a in st["destination_audit"])
    ans = c.get("/api/protocols/search", params={"q": "Stroke Alert Patient Time Last Known Well twenty-four hours"}).json()
    assert ans["results"][0]["section"] == "3.1"
    assert c.get("/api/protocols/700-A13/page/1").headers["content-type"] == "image/png"
    assert "protocols" in c.get("/api/state").json()
