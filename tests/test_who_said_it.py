"""Who said it, from the words (owner's decision, 2026-09-26): the room microphone cannot tell voices apart, so the
check step reads whose information each fact is ("medic", "patient", "husband") and the patient's name when the words
state it. The medic's own treatment may then confirm itself; history told by anyone stays a tap. The handoff report
says who told us what."""
import time

from fakes import FakeModel, make_client
from test_fact_verify import _recording, _SaidSTT
from herald.core.confirmation import ConfirmationPolicy
from herald.core.schema import CapturedBy, FactIn, Provenance, Role, Status
from herald.core.vocabulary import default_vocabulary
from herald.extraction.verify import FactVerifier, schema_for
from herald.reporting.informants import informants, informants_sentence

VOCAB = default_vocabulary()
POLICY = ConfirmationPolicy(VOCAB, 0.8, room_mic=(True, frozenset({"allergies", "meds.given", "patient.name"})),
                            medic_report_confirms=frozenset({"meds.given"}))


class _Judge:
    """Answers the check step from a script: {fact number: said_by}, every fact kept, and a patient name."""

    def __init__(self, said_by: dict[int, str], name: str = ""):
        self.said_by, self.name, self.seen = said_by, name, []

    def chat_json(self, system, user, *, schema=None, **_):
        self.seen.append((system, user, schema))
        return {"patient_name": self.name,
                "facts": [{"n": n, "keep": True, "said_by": w, "why": "scripted"} for n, w in self.said_by.items()]}


def test_the_check_step_says_whose_information_each_fact_is():
    facts = [FactIn(key="allergies", value=["penicillin"]), FactIn(key="vitals.hr", value=116),
             FactIn(key="symptom.onset", value="40 minutes ago")]
    r = FactVerifier(_Judge({1: "husband", 2: "medic", 3: "unclear"}), VOCAB).read("words", facts)
    assert [f.provenance.heard_as for f in r.kept] == ["husband", "medic", None]
    assert r.said_by == {1: "husband", 2: "medic"}


def test_the_answer_is_limited_to_the_vocabulary_words_and_a_name():
    s = schema_for(2, FactVerifier(_Judge({}), VOCAB).said_by)
    said_by = s["properties"]["facts"]["items"]["properties"]["said_by"]["enum"]
    assert {"medic", "patient", "husband", "neighbor", "relative", "unclear"} <= set(said_by)
    assert list(s["properties"]) == ["patient_name", "facts"]                 # the name before the facts
    assert list(s["properties"]["facts"]["items"]["properties"]) == ["n", "keep", "said_by", "why"]
    assert list(schema_for(0, said_by)["properties"]) == ["patient_name"]     # no facts: asked only for the name


def test_a_name_is_read_from_the_words_never_invented():
    read = lambda name, words: FactVerifier(_Judge({}, name), VOCAB).read(words, []).patient_name   # noqa: E731
    assert read("Robert Chen", "His name is Robert Chen. He's 62.") == "Robert Chen"
    assert read("Robert Chen", "He's 62 and his chest hurts.") is None                  # not in the words
    assert read("RACE of six, screens positive for LVO", "RACE of six, screens positive for LVO.") is None
    assert read("", "Clearing St. Luke's.") is None
    assert read("My Band", "It's like my band.") is None                               # not a name as said


def heard(key, value, heard_as, role, *, confidence=0.95):
    return FactIn(key=key, value=value, role=role, captured_by=CapturedBy.other, confidence=confidence,
                  speaker=heard_as, provenance=Provenance(checked=True, heard_as=heard_as))


def status(fin):
    return POLICY.initial_status(fin, None, fin.value)


def test_the_medics_own_treatment_confirms_itself_history_from_anyone_waits():
    assert status(heard("meds.given", {"drug": "aspirin"}, "medic", Role.medic)) == Status.confirmed
    assert status(heard("meds.given", {"drug": "aspirin"}, "medic", Role.medic, confidence=0.5)) == Status.unconfirmed
    assert status(heard("allergies", ["penicillin"], "medic", Role.medic)) == Status.unconfirmed
    assert status(heard("meds.given", {"drug": "aspirin"}, "husband", Role.family)) == Status.unconfirmed
    assert status(heard("allergies", ["penicillin"], "husband", Role.family)) == Status.unconfirmed


def test_other_room_mic_facts_confirm_as_before_whoever_said_them():
    assert status(heard("symptom.onset", "40 minutes ago", "husband", Role.family)) == Status.confirmed
    assert status(heard("vitals.hr", 116, "medic", Role.medic)) == Status.confirmed
    named_mic = FactIn(key="vitals.hr", value=96, role=Role.family, speaker="wife", captured_by=CapturedBy.other,
                       confidence=0.95, provenance=Provenance(checked=True))       # the wife's own mic, not the room
    assert status(named_mic) == Status.unconfirmed


def _room_mic_says(tmp_path, words, rows, judge):
    client, ctx = make_client(model=FakeModel(rows=rows), audio_dir=tmp_path)
    ctx.stt, ctx.fact_verifier = _SaidSTT(words), FactVerifier(judge, VOCAB)
    with client:
        assert client.post("/api/audio", files=_recording(),
                           data={"incident_id": ctx.incident.id, "ambient": "true"}).status_code == 200
        deadline = time.monotonic() + 2
        while ctx.speech_in_flight and time.monotonic() < deadline:
            time.sleep(.01)
    return ctx


def test_room_mic_facts_carry_who_said_them_and_the_name_waits_for_a_tap(tmp_path):
    words = "His name is Robert Chan. He takes metoprolol. Should I call our daughter?"
    ctx = _room_mic_says(tmp_path, words, [["meds.list", ["metoprolol"], "m"]], _Judge({1: "relative"}, "Robert Chan"))
    by_key = {}
    for f in ctx.incident.facts:
        by_key.setdefault(f.key, f)
    assert by_key["meds.list"].speaker == "relative" and by_key["meds.list"].role == Role.family
    name = by_key["patient.name"]
    assert name.value == "Robert Chan" and name.status == Status.unconfirmed
    assert name.provenance.extractor.startswith("check:")


def test_the_report_says_who_told_us_what():
    src = lambda key, role, speaker=None: {"key": key, "role": role, "speaker": speaker}   # noqa: E731
    sections = [{"lines": [
        {"status": "confirmed", "sources": [src("vitals.hr", "device", "monitor"), src("patient.age", "medic")]},
        {"status": "confirmed", "sources": [src("allergies", "family", "husband"), src("meds.list", "family", "husband")]},
        {"status": "missing", "sources": [src("symptom.onset", "family", "husband")]},
        {"status": "confirmed", "sources": [src("complaint.chief", "unknown", "Speaker not identified")]},
    ]}]
    words = {"heading": "Who told us", "rest": "the rest",
             "labels": {"medic": "medic", "device": "patient monitor", "unknown": "speaker not identified"}}
    rows = informants(sections, VOCAB, words)
    assert [(r["who"], r["items"]) for r in rows] == [
        ("husband", ["Allergies", "Medications"]), ("patient monitor", ["Heart rate"]), ("medic", ["Age"]),
        ("speaker not identified", ["Chief complaint"])]
    assert informants_sentence(rows, words, "; ", ", ") == (
        "Who told us: husband: allergies, medications; patient monitor: heart rate; medic: the rest; "
        "speaker not identified: chief complaint.")


def test_a_new_alert_is_named_by_its_label_not_its_key():
    from herald.api.trace import TraceRecorder
    alert = {"type": "confirm_required", "key": "patient.name", "label": "Patient name (reported)"}
    before = {"readiness": {}, "alerts": set(), "alert_labels": {}, "scores": {}, "missing": set()}
    after = {**before, "alerts": {("confirm_required", "patient.name")},
             "alert_labels": {("confirm_required", "patient.name"): alert["label"]}}
    assert TraceRecorder.diff(before, after)["alerts_new"] == [{"type": "confirm_required", "label": "Patient name (reported)"}]
