"""Protocol key points: the model chooses among the county's sentences; nothing it writes reaches the screen."""
from herald.knowledge.cues import ProtocolCues
from herald.knowledge.keypoints import KeyPointPicker, sentences

P32 = {"doc": "700-A13", "section": "3.2", "text": "3.2. If patient has four (4) points on the G.F.A.S.T stroke screening "
       "transport the patient to a Comprehensive Stroke Center (Policy 602)."}
P321 = {"doc": "700-A13", "section": "3.2.1", "text": "3.2.1. If transport time to closest Comprehensive Stroke Center is "
        "greater than forty-five (45) minutes, transport the patient to the closest Primary Stroke Center."}
LIST = {"doc": "602", "section": "VI.E.1", "text": "1. Patients meeting Comprehensive Stroke Alert Criteria shall be transported to:"}


class FakeModel:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat_json(self, system, user, **kw):
        self.calls.append(user)
        return self.reply


def test_sentences_drop_numbering_and_bare_lead_ins():
    assert sentences(P32)[0].startswith("If patient has four (4) points")
    assert sentences(LIST) == []


def test_only_the_countys_sentences_and_verbatim_phrases_survive():
    model = FakeModel({"points": [
        {"n": 2, "mark": ["greater than forty-five (45) minutes", "Primary Stroke Center"]},
        {"n": 1, "mark": ["four (4) points", "go to the nearest hospital"]},     # not in the sentence: dropped
        {"n": 9, "mark": []},                                                     # invented sentence number: dropped
        {"n": 2, "mark": []}]})                                                   # repeated: dropped
    points = KeyPointPicker(model).pick("68 F suspected stroke; G.F.A.S.T. 4 of 4", [P32, P321, LIST])
    assert [p["cite"] for p in points] == ["700-A13 §3.2.1", "700-A13 §3.2"]
    assert points[0]["text"] == sentences(P321)[0]
    assert points[1]["marks"] == ["four (4) points"]
    assert "68 F suspected stroke" in model.calls[0] and "[3]" not in model.calls[0]   # the bare lead-in is never offered


def test_cues_carry_the_picked_points_and_survive_a_picker_failure():
    class KB:
        def answer(self, query, k):
            return {"answerable": True, "chosen": 2, "results": [P32, P321]}
    snap = {"incident": {"id": "i", "dispatch": "possible stroke"}, "summary": "68 F", "alerts": [{"type": "gfast_positive",
            "label": "G.F.A.S.T."}], "readiness": [{"id": "stroke", "label": "Stroke alert"}]}
    good = ProtocolCues(lambda: KB(), lambda: "sc", picker=KeyPointPicker(FakeModel({"points": [{"n": 1, "mark": []}]})))
    for cue in good.pending(snap):
        good.resolve(cue)
    assert good.view(snap)[0]["points"][0]["cite"] == "700-A13 §3.2"

    class Down:
        def pick(self, *a):
            raise RuntimeError("model down")
    down = ProtocolCues(lambda: KB(), lambda: "sc", picker=Down())
    for cue in down.pending(snap):
        down.resolve(cue)
    first = down.view(snap)[0]
    assert first["state"] == "found" and "points" not in first      # the passages still show; the screen falls back
