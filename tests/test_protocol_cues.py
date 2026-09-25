"""Situational protocol lookup: the county's words for the situation Herald recognises, never a model's."""
from herald.knowledge.cues import ProtocolCues

PASSAGE = {"doc": "700-A13", "title": "Stroke", "section": "3.2", "heading": "If patient has four (4) points",
           "page": 2, "effective": "January 1, 2026", "text_layer_uncertain": False,
           "text": "3.2. If patient has four (4) points on the G.F.A.S.T stroke screening transport the patient to a "
                   "Comprehensive Stroke Center."}


class FakeKB:
    def __init__(self, answer):
        self.answer_value, self.queries = answer, []

    def answer(self, query, k):
        self.queries.append(query)
        return self.answer_value


def cues(kb):
    return ProtocolCues(lambda: kb, lambda: "santa_clara")


STROKE = {"alerts": [{"type": "gfast_positive"}], "readiness": [{"id": "stroke"}]}


def test_a_positive_stroke_screen_brings_the_county_destination_rule_verbatim():
    kb = FakeKB({"answerable": True, "reranked": True, "chosen": 1, "results": [PASSAGE, {**PASSAGE, "section": "9.9"}]})
    c = cues(kb)
    assert [v["state"] for v in c.view(STROKE)] == ["searching", "searching"]    # before the search, never a guess
    for cue in c.pending(STROKE):
        c.resolve(cue)
    first = c.view(STROKE)[0]
    assert first["id"] == "stroke_destination" and first["state"] == "found"
    assert [p["section"] for p in first["passages"]] == ["3.2"]                  # only what the reranker chose
    assert first["passages"][0]["text"] == PASSAGE["text"]                       # the document's words, unchanged
    assert first["passages"][0]["effective"] == "January 1, 2026"
    assert c.pending(STROKE) == []                                               # searched once, then cached


def test_nothing_is_shown_without_a_situation_and_the_documents_can_say_no():
    kb = FakeKB({"answerable": False, "reranked": True, "results": [PASSAGE]})
    c = cues(kb)
    assert c.view({"alerts": [], "readiness": []}) == []
    sepsis = {"alerts": [{"type": "sepsis_prenotification"}], "readiness": []}
    for cue in c.pending(sepsis):
        c.resolve(cue)
    view = c.view(sepsis)
    assert view[0]["state"] == "not_covered" and view[0]["passages"] == []        # not the nearest passage


def test_a_failed_search_is_retried_rather_than_cached():
    class Broken(FakeKB):
        def answer(self, query, k):
            raise RuntimeError("model down")
    c = cues(Broken(None))
    todo = c.pending(STROKE)
    for cue in todo:
        c.resolve(cue)
    assert len(c.pending(STROKE)) == len(todo)


def test_protocol_lookup_off_means_no_cues():
    c = ProtocolCues(lambda: None, lambda: "santa_clara")
    assert c.view(STROKE) == [] and c.pending(STROKE) == []


def test_long_passages_are_shortened_at_a_sentence_and_marked():
    long = {**PASSAGE, "text": "First sentence here. " * 60}
    c = cues(FakeKB({"answerable": True, "chosen": 1, "results": [long]}))
    for cue in c.pending(STROKE):
        c.resolve(cue)
    p = c.view(STROKE)[0]["passages"][0]
    assert p["shortened"] and p["text"].endswith(" …") and len(p["text"]) <= 702
