"""Protocol lookup (P9) against the archived county documents and the answer keys in eval/protocols/."""
import copy
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import httpx
import pytest

from fakes import make_client
from herald.config import load_text
from herald.knowledge import KnowledgeBase, ProtocolSync, document_for_page
from herald.knowledge.pdf import normalize, page_texts
from herald.knowledge.tables import read_check_table

ROOT = Path(__file__).resolve().parent.parent
COUNTY = json.loads((ROOT / "config/counties/santa_clara.json").read_text())
ARCHIVE = ROOT / "data/protocols/santa_clara/archive"
KEYS = ROOT / "eval/protocols"
SECTIONS_KEY = [json.loads(line) for line in open(KEYS / "sections_key.jsonl")]
# Change memos in the archive: they describe differences between protocol versions, so they are reference reading
# and are not indexed as protocol text (eval/protocols/README.md).
REFERENCE_ONLY = {"2025-policy-protocol-changes-summary.pdf", "2026-policy-protocol-changes-summary.pdf"}


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase(COUNTY, ROOT / "data/protocols")


def _section(kb, doc_id, number):
    return [s for s in kb.sections if (s.doc_id, s.number) == (doc_id, number)]


def test_every_numbered_section_in_the_key_is_found_and_nothing_else(kb):
    """All 32 documents: the splitter's numbered sections equal the CPU-built key (number, page and level), so a
    lost item and a spurious one (a wrapped "90 mmHg" line read as section 90) both fail. Key rows on pages no
    document covers (the AO memo and redline copies) are skipped; 602 and 605 share one PDF."""
    want = Counter((document_for_page(COUNTY, k["doc"], k["page"]), k["number"], k["page"], k["level"])
                   for k in SECTIONS_KEY if k["kind"] == "section" and document_for_page(COUNTY, k["doc"], k["page"]))
    got = Counter((s.doc_id, s.number, s.page, s.level) for s in kb.sections
                  if s.number != "0" and not s.number.startswith("Table"))
    assert not want - got, sorted(want - got)[:10]
    assert not got - want, sorted(got - want)[:10]
    assert {d for d, *_ in want} == {d["id"] for d in COUNTY["documents"]}     # every document is in the key


def test_document_for_page_splits_a_file_that_holds_two_policies():
    ao = "AO-2025-005_policy-602-destination_eff-2025-04-01.pdf"
    assert [document_for_page(COUNTY, ao, p) for p in (1, 5, 12, 21, 23, 25, 27)] == \
        [None, None, "602", "602", None, "605", "605"]
    assert document_for_page(COUNTY, "700-A04_sepsis_eff-2026-01-01.pdf", 1) == "700-A04"


def test_every_current_archive_document_is_indexed_and_no_superseded_one(kb):
    files = {Path(d["file"]).name for d in COUNTY["documents"]}
    current = {p.name for p in ARCHIVE.glob("*.pdf")}
    assert current - files == REFERENCE_ONLY
    assert not any("previous/" in d["file"] for d in COUNTY["documents"])
    # a document that also has an older copy in archive/previous/ is indexed at a later effective date than it
    for old in (ARCHIVE / "previous").glob("*.pdf"):
        doc_id = old.name.split("_")[0]
        if doc_id in kb.versions:
            m = re.search(kb.cfg["effective_pattern"], page_texts(old, (1, 1))[0][1])
            assert kb.versions[doc_id]["effective_date"] > kb._calendar_date(m.group(1)), doc_id


def test_every_effective_date_is_read_from_the_file_and_matches_the_reviewed_date(kb):
    """The printed date is read from each file ("January 1, 2026", "Effective Date: 1/1/2026" in 302 and 410) and
    must equal the reviewed date in the county config."""
    assert len(kb.versions) == len(COUNTY["documents"]) == 32
    for doc in COUNTY["documents"]:
        v = kb.versions[doc["id"]]
        assert v["effective_in_file"], doc["id"]
        assert v["effective_date"] == doc["effective"], (doc["id"], v["effective_in_file"])
    assert kb.versions["302"]["effective_in_file"] == "1/1/2026"
    assert kb.versions["605"]["effective_in_file"] == "April 1, 2025"       # page 25 of the AO file


def test_every_figure_page_in_the_key_is_configured():
    """Pages whose content is an image (or a chart in a font with no character map) are read by the vision model:
    each figure page found with CPU tools is declared in the county config, on the section that holds it."""
    in_key = {(document_for_page(COUNTY, k["doc"], k["page"]), k["page"], k["number"])
              for k in SECTIONS_KEY if k["kind"] == "figure"}
    configured = {(d["id"], f["page"], f["section"]) for d in COUNTY["documents"] for f in d.get("figures", [])}
    assert in_key == configured and len(configured) == 8


def test_body_text_printed_on_two_pages_is_not_a_running_line(kb):
    """700-A14 prints the same SVT definition in §5.1 (page 1) and §7.1 (page 2); both keep it, while the running
    header and footer are still removed."""
    for number in ("5.1", "7.1"):
        (s,) = _section(kb, "700-A14", number)
        assert "absent P waves" in s.text
    assert not any("Prehospital Care Manual" in s.text or "Page 2 of 3" in s.text
                   for s in kb.sections if s.doc_id == "700-A14")
    assert not any("POLICY ##102" in s.text for s in kb.sections if s.doc_id == "430")      # side tab
    (inventory,) = _section(kb, "302", "III.A")
    assert "Non-Transport" in inventory.text                                                # table column header


def test_policy_410_deep_outline_levels(kb):
    (s,) = _section(kb, "410", "IV.B.1.b.i.1.a")
    assert s.level == 7 and s.text.startswith("a. Must have current nationally recognized")
    assert [x.level for x in _section(kb, "410", "IV.B.1.a.viii")] == [5]
    assert [x.title for x in _section(kb, "410", "I")] == [      # the Roman numbering restarts at "I. References"
        "Purpose: Provide the procedures and standards for the Santa Clara County EMS for Children (EMSC) Care",
        "References:"]


def test_policy_605_prints_roman_ii_twice(kb):
    assert [s.title for s in _section(kb, "605", "II")] == ["Trauma Alert Patient", "Trauma Alert – Ambulance Transport"]
    (w,) = _section(kb, "605", "II.W")
    assert "Fall from height > 10 feet" in w.text


def test_items_that_start_with_a_dose_or_hold_only_a_table_are_sections(kb):
    (s,) = _section(kb, "700-A10", "3.2")
    assert s.title.startswith("500 ml Normal Saline bolus")
    assert not _section(kb, "700-A10", "90")                # "90 mmHg", the wrapped end of 3.2, is not a section
    (t,) = _section(kb, "700-P10", "3.3.1.3")
    assert "Weight in kg" in t.text and "0.003" in t.text


def test_text_layer_damage_is_flagged_not_silently_repaired(kb):
    """700-A18 sets "≥" in a Symbol font that the text layer reports as "³"; kept as printed (NFKC would read
    "SBP 3 140") and flagged, so the page image is offered. 700-P07's flowchart pages are symbol runs."""
    assert normalize("SBP ³ 140, 90º, Diﬃculties") == "SBP ³ 140, 90º, Difficulties"
    for number in ("6.1.2", "6.1.3"):
        (s,) = _section(kb, "700-A18", number)
        assert s.uncertain and "³" in s.text
    (chart,) = _section(kb, "700-P07", "15")
    assert chart.uncertain
    assert not any(s.uncertain for s in kb.sections if s.doc_id in ("700-A04", "700-A16", "700-S06"))


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


class _Reader:
    """A vision model stand-in that records each figure transcription (the page it was shown and the prompt)."""

    def __init__(self, name):
        self.name, self.calls, self.prompts = name, 0, []

    def model_name(self):
        return self.name

    def chat_json(self, system, user, **kw):
        self.calls += 1
        self.prompts.append(user)
        return {"steps": [f"step read by {self.name}"]}


def _county_with_figures(tmp_path):
    """Only the documents that declare figures, copied to a scratch protocols folder (keeps the test quick)."""
    county = copy.deepcopy(COUNTY)
    county["documents"] = [d for d in county["documents"] if d.get("figures")]
    (tmp_path / "santa_clara" / "archive").mkdir(parents=True)
    for d in county["documents"]:
        shutil.copy(ARCHIVE / Path(d["file"]).name, tmp_path / "santa_clara" / "archive")
    return county


def test_figure_transcription_is_cached_per_vision_model(tmp_path):
    """Each figure is read once per document version and vision model: a second build with the same model makes
    no new calls, and switching models re-reads every figure instead of reusing the other model's transcription.
    A figure that is not a flowchart (700-M09's ECG chart) is read with its own prompt."""
    county = _county_with_figures(tmp_path)
    n = sum(len(d["figures"]) for d in county["documents"])
    assert n == 8
    a, b = _Reader("omni"), _Reader("qwen3vl-fp8")
    KnowledgeBase(county, tmp_path, vision=a)
    KnowledgeBase(county, tmp_path, vision=a)          # cached: no second call
    kb = KnowledgeBase(county, tmp_path, vision=b)
    assert (a.calls, b.calls) == (n, n)
    for d in county["documents"]:                      # every figure's text joins the section it belongs to
        for f in d["figures"]:
            (s,) = [x for x in kb.sections if (x.doc_id, x.number) == (d["id"], f["section"])]
            assert f"{f['title']}, page {f['page']}" in s.text and "step read by qwen3vl-fp8" in s.text
    chart, flow = load_text("prompts/figure_transcribe_chart.md"), load_text("prompts/figure_transcribe.md")
    assert a.prompts.count(chart) == 1 and a.prompts.count(flow) == n - 1


@pytest.mark.parametrize("query,doc,section", [
    ("SIRS criteria two or more advanced notification to hospital of suspected sepsis", "700-A04", "1.4"),
    ("Tranexamic Acid 2,000 mg in 100 ml Normal Saline over 10 minutes", "700-A16", "3.4"),
    ("tourniquet placed for over two hours back off every five minutes", "700-M17", "2.5"),
    ("fell more than 72 hours ago Red Prehospital Trauma Triage criteria not required", "700-S06", "1.11"),
])
def test_search_finds_the_new_protocols(kb, query, doc, section):
    r = kb.search(query, 3)[0]
    assert (r["doc"], r["section"]) == (doc, section)
    assert r["effective"] == next(v["effective_in_file"] for d, v in kb.versions.items() if d == doc)


def test_every_qa_gold_citation_resolves_to_a_section_that_holds_the_quote(kb):
    """eval/protocols/qa_gold.jsonl: each answer cites a section the knowledge base indexes, and a quoted answer is
    in the text of that section and its sub-items (qa15 quotes list items a-d of III.A.1), except where the words
    exist only in a figure image or in a flagged, damaged text layer (qa02's G.F.A.S.T. box, qa06's flowchart)."""
    import unicodedata
    flat = lambda s: " ".join(unicodedata.normalize("NFKC", s).split())
    figures = {(d["id"], f["page"]) for d in COUNTY["documents"] for f in d.get("figures", [])}
    rows = [json.loads(line) for line in open(KEYS / "qa_gold.jsonl")]
    assert len({r["id"] for r in rows}) == len(rows) == 59
    for r in rows:
        if r["answer_type"] == "unanswerable":
            assert (r["doc"], r["section"], r["page"], r["answer_quote"]) == (None, None, None, None), r["id"]
            continue
        doc = document_for_page(COUNTY, r["doc"], r["page"])
        secs = _section(kb, doc, r["section"]) if r["answer_type"] == "quote" else \
            [s for s in kb.sections if s.doc_id == doc and s.number == r["section"]]
        assert secs, r["id"]
        if r["answer_type"] == "quote" and (doc, r["page"]) not in figures and not any(s.uncertain for s in secs):
            with_items = " ".join(s.text for s in kb.sections if s.doc_id == doc
                                  and (s.number == r["section"] or s.number.startswith(r["section"] + ".")))
            assert flat(r["answer_quote"]) in flat(with_items), r["id"]


# ── the sync manifest is read on the GET /api/state path, so it must never raise ──
# summary() feeds herald/api/context.py full_state(), which is what the medic screen polls. On 2026-09-25 the app
# returned 500 from /api/state during startup: manifest.json existed but was zero-length, because the file is
# rewritten while the protocol index builds, and _manifest() guarded only for the file being absent. The fields it
# provides (review_required, last_sync) are optional, so an unreadable manifest must degrade to {} rather than take
# the whole snapshot down with it.
@pytest.mark.parametrize("content, why", [
    ("", "zero-length, which is what a half-written file looks like"),
    ("   \n", "whitespace only"),
    ('{"501": {"review_required": true}', "truncated mid-object"),
    ("not json at all", "not json"),
    ("null", "valid json but not an object"),
])
def test_an_unreadable_manifest_degrades_instead_of_failing_the_snapshot(tmp_path, content, why):
    county = copy.deepcopy(COUNTY)
    county["documents"] = []                      # no documents: summary() still has to answer
    kb = KnowledgeBase(county, tmp_path)
    # _manifest() reads <protocols_dir>/<county id>/manifest.json, not <protocols_dir>/manifest.json. Writing it to
    # the wrong place makes this test pass for the wrong reason (the file simply does not exist), so assert it landed.
    manifest = tmp_path / county["id"] / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(content)
    assert kb.dir == manifest.parent
    s = kb.summary()                              # must not raise, whatever is in the file
    assert s["county"] == county["id"], f"summary() lost its county with a manifest that is {why}"
    assert s["review_required"] == []
    assert s["last_sync"] is None


def test_a_good_manifest_is_still_read(tmp_path):
    """The degradation above must not swallow a manifest that is fine."""
    county = copy.deepcopy(COUNTY)
    county["documents"] = []
    kb = KnowledgeBase(county, tmp_path)
    manifest = kb.dir / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(
        {"_last_sync": "2026-09-25T00:00:00Z", "501": {"review_required": True}, "605": {"review_required": False}}))
    s = kb.summary()
    assert s["last_sync"] == "2026-09-25T00:00:00Z"
    assert s["review_required"] == ["501"]

def test_a_lead_in_section_carries_the_items_listed_under_it(kb):
    """602 §VI.E.1 ends "Stroke shall be transported to:"; the destinations are its sub-items. A quote of it must hold
    the rule, and the sub-items stay their own citable sections."""
    by = {(s.doc_id, s.number): s for s in kb.sections}
    lead = by[("602", "VI.E.1")]
    subs = [s for (d, n), s in by.items() if d == "602" and n.startswith("VI.E.1.")]
    assert subs, "the destinations are sub-items of VI.E.1"
    assert subs[0].text in lead.items
    hit = next(r for r in kb.search("stroke alert patients destination comprehensive stroke center", 8) if (r["doc"], r["section"]) == ("602", "VI.E.1"))
    assert not hit["text"].rstrip().endswith(":")             # a quote of the lead-in holds its items


def test_the_lead_in_carry_is_bounded_and_stops_at_the_next_sibling():
    from herald.knowledge.sections import SectionSplitter
    from herald.config import load_yaml
    cfg = load_yaml("knowledge.yaml")
    split = SectionSplitter(cfg["heading_styles"], cfg["running_line_share"], cfg["glyph_error_pattern"],
                            cfg.get("running_line_band"), 60).split
    text = "\n".join(["I. Destinations", "A. Stroke patients shall be transported to:", "1. The closest center.",
                      "2. Another center that is further away than the first one.", "B. Trauma patients go elsewhere."])
    s = {x.number: x for x in split("t", [(1, text)], "outline")}
    assert "1. The closest center." in s["I.A"].items         # within the budget
    assert "Another center" not in s["I.A"].items            # over the 60-character budget
    assert "Trauma" not in s["I.A"].items                    # the next sibling is not a sub-item
    assert "closest" not in s["I.A"].text                    # the indexed text is unchanged
