"""Destination by voice or by one tap (owner, 2026-09-26: "the medic will not go to a drop-down"): the crew's words
that name one county hospital set it; words that name none stay heard; while none is set, Herald suggests ONE
hospital from the county's own destination rules, accepted with a tap or by saying it."""
import asyncio
from datetime import datetime, timezone

from fakes import make_client
from herald.config.county import CountyRegistry
from herald.core.schema import CapturedBy, FactIn, Role, Status
from herald.transport import DestinationPolicy, DestinationResolver, Situation, TransportService, facilities
from herald.transport.service import NOT_MATCHED

COUNTY = CountyRegistry("santa_clara").active
OPTIONS = facilities(COUNTY)
CFG = {"position_stale_s": 120, "recompute_moved_m": 75, "recompute_every_s": 30, "max_accuracy_m": 500}
HERE = (37.3352, -121.8811)                      # SJSU


class Chooser:
    """The local model's reply to the destination prompt."""
    def __init__(self, *matches):
        self.matches, self.calls = list(matches), []

    def chat_json(self, system, user, **kw):
        self.calls.append((user, kw["schema"]))
        return {"matches": self.matches}


class Minutes:
    """A road router with a set drive time (minutes) per county hospital."""
    def __init__(self, **minutes):
        self.minutes = minutes

    async def table(self, origin, destinations):
        ids = [f.id for f in OPTIONS if f.routable]
        return [(self.minutes.get(i, 30) * 60.0, self.minutes.get(i, 30) * 900.0) for i in ids]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def client_with(model=None, router=None):
    client, ctx = make_client()
    clock = Clock()
    ctx.transport = TransportService(lambda: COUNTY, router, DestinationResolver(model), CFG, clock)
    if router is not None:
        asyncio.run(ctx.transport.update_position(*HERE, 10.0))
    return client, ctx


def say(inc, value, confidence=0.99, **kw):
    """The medic's own mic (crew speech), or another speaker with captured_by/role."""
    return inc.ingest(FactIn(key="transport.destination", value=value, confidence=confidence, **kw))


def run_match(ctx):
    """One pass of the background loop (herald/api/app.py match_loop)."""
    for heard in ctx.transport.pending_matches(ctx.incident):
        ctx.transport.match(heard)
    return ctx.transport.settle(ctx.incident)


def transport(client):
    return client.get("/api/state").json()["transport"]


def confirm(inc, key, value):
    return inc.set_status(inc.ingest(FactIn(key=key, value=value)).id, Status.confirmed)


# ---------- matching the words ----------
def test_official_name_matches_without_the_model_and_only_one_listed_id_is_a_match():
    model = Chooser("GSH")
    r = DestinationResolver(model)
    assert r.resolve("good samaritan hospital", OPTIONS) == "GSH" and r.resolve("RSJ", OPTIONS) == "RSJ" and not model.calls
    assert r.resolve("Good Sam", OPTIONS) == "GSH"
    items = model.calls[0][1]["properties"]["matches"]["items"]
    assert items["enum"] == [f.id for f in OPTIONS]                              # it can only name listed ids
    assert DestinationResolver(Chooser("ECH", "LGH")).resolve("El Camino", OPTIONS) is None     # two campuses
    assert DestinationResolver(Chooser()).resolve("the gas station", OPTIONS) is None
    assert DestinationResolver(Chooser("MADE-UP")).resolve("somewhere", OPTIONS) is None


# ---------- voice: the crew's words set it ----------
def test_the_exact_spoken_name_sets_the_destination_without_the_model():
    model = Chooser()
    client, ctx = client_with(model)
    said = say(ctx.incident, "Regional Medical Center of San Jose", confidence=0.3)   # below the auto-confirm bar
    assert said.status == Status.unconfirmed
    assert run_match(ctx) == "set" and not model.calls
    d = transport(client)["destination"]
    assert d == {**d, "id": "RSJ", "how": "heard", "said": "Regional Medical Center of San Jose"}
    fact = ctx.incident.latest("transport.destination", confirmed_only=True)
    assert fact.provenance.normalized[0] == {"said": "Regional Medical Center of San Jose",
                                             "value": "Regional Medical Center of San Jose",
                                             "system": "county-facility", "code": "RSJ", "method": "exact"}


def test_the_models_single_pick_sets_the_destination_with_what_was_said():
    client, ctx = client_with(Chooser("RSJ"))
    said = say(ctx.incident, "Regional")
    assert run_match(ctx) == "set"
    fact = ctx.incident.latest("transport.destination", confirmed_only=True)
    assert fact.value == "Regional Medical Center of San Jose" and fact.provenance.extractor == "transport:heard"
    assert fact.provenance.normalized[0]["method"] == "model" and fact.provenance.normalized[0]["said"] == "Regional"
    assert next(f for f in ctx.incident.facts if f.id == said.id).status == Status.rejected   # kept as evidence
    assert ctx.incident.audit_log[-1] == {**ctx.incident.audit_log[-1], "action": "fact_settled", "actor": "herald",
                                          "replaced_value": "Regional", "value": fact.value}
    t = transport(client)
    assert t["destination"]["how"] == "heard" and t["heard"] is None and t["suggestion"] is None
    assert client.get("/api/state").json()["facts"]["transport.destination"]["status"] == "confirmed"


def test_words_that_name_no_single_hospital_stay_heard_and_are_not_the_destination():
    client, ctx = client_with(Chooser("KSC", "STH"))
    said = say(ctx.incident, "Kaiser")
    assert said.status == Status.confirmed                                     # the medic's mic, as captured
    assert run_match(ctx) == "held"
    assert ctx.incident.latest("transport.destination", confirmed_only=True) is None
    fact = next(f for f in ctx.incident.facts if f.id == said.id)
    assert fact.status == Status.unconfirmed and NOT_MATCHED in fact.provenance.hold_reason
    t = transport(client)
    assert t["destination"] is None and t["heard"] == {**t["heard"], "value": "Kaiser", "state": "unmatched", "id": None}
    assert t["suggestion"]["basis"] == "policy"                                 # Herald's one hospital, below it
    assert run_match(ctx) is None                                              # held once
    ctx.incident.set_status(said.id, Status.confirmed)                         # the medic confirms it as said
    assert run_match(ctx) is None and ctx.incident.latest("transport.destination", confirmed_only=True).value == "Kaiser"


def test_a_later_spoken_hospital_replaces_the_destination_and_both_changes_are_audited():
    client, ctx = client_with(Chooser("RSJ"))
    say(ctx.incident, "Regional")
    run_match(ctx)
    ctx.transport.resolver = DestinationResolver(Chooser("GSH"))
    say(ctx.incident, "actually Good Sam")
    assert run_match(ctx) == "set"
    assert transport(client)["destination"] == {**transport(client)["destination"], "id": "GSH", "said": "actually Good Sam"}
    settled = [a for a in ctx.incident.audit_log if a["action"] == "fact_settled"]
    assert [a["value"] for a in settled] == ["Regional Medical Center of San Jose", "Good Samaritan Hospital"]
    # a later word that names none leaves the destination where it was, and shows what was heard
    ctx.transport.resolver = DestinationResolver(Chooser())
    say(ctx.incident, "the gas station")
    run_match(ctx)
    t = transport(client)
    assert t["destination"]["id"] == "GSH" and t["heard"]["value"] == "the gas station"


def test_another_speakers_hospital_is_only_suggested():
    client, ctx = client_with(Chooser("GSH"))
    heard = say(ctx.incident, "Good Sam", role=Role.family, captured_by=CapturedBy.other)
    assert heard.status == Status.unconfirmed
    assert run_match(ctx) is None
    t = transport(client)
    assert t["destination"] is None and t["suggestion"] == {**t["suggestion"], "id": "GSH", "basis": "heard"}


# ---------- agentic: Herald suggests one ----------
def test_a_stroke_alert_without_a_destination_gets_the_closest_comprehensive_stroke_center_and_accepting_sets_it():
    client, ctx = client_with(router=Minutes(ECH=31, GSH=14, KSC=18, RSJ=9, SUH=40, VMC=6, OCH=7))
    for item in ("gaze", "facial", "arm_leg", "speech"):
        confirm(ctx.incident, f"exam.gfast.{item}", 1)                          # G.F.A.S.T. 4 of 4
    s = transport(client)["suggestion"]
    assert s == {**s, "id": "RSJ", "basis": "policy", "rule": "stroke_comprehensive", "minutes": 9,
                 "nearest_known": True, "service": "Comprehensive Stroke Center"}     # not VMC (6), not OCH (7)
    assert s["cite"].startswith("602 §VI.E.1") and "Comprehensive Stroke Center" in s["quote"]
    h = {"X-Herald-Patient": ctx.incident.id}
    assert client.post("/api/transport/destination", json={"facility": "RSJ", "via": "suggestion"}, headers=h).status_code == 200
    t = transport(client)
    assert t["destination"] == {**t["destination"], "id": "RSJ", "how": "suggested"} and t["suggestion"] is None
    assert t["eta"]["source"] == "route"


def test_a_stroke_center_suggestion_without_a_position_follows_the_county_list_and_says_nearest_is_unknown():
    client, ctx = client_with()
    ctx.incident.dispatch = "possible stroke"
    s = transport(client)["suggestion"]
    assert s == {**s, "rule": "stroke", "id": "ECH", "minutes": None, "nearest_known": False}   # first on the list
    assert "4 of 4" in s["note"]


def test_the_county_rules_pick_the_center_for_each_situation():
    policy = DestinationPolicy(COUNTY)
    assert policy.problems(OPTIONS) == []
    drive = lambda minutes: (lambda fid: (minutes.get(fid, 30) * 60.0, 1000.0))
    near = drive({"SLH": 5, "ECH": 50, "GSH": 55, "KSC": 60, "RSJ": 48, "SUH": 70, "OCH": 12, "VMC": 20, "STH": 25})
    pick = lambda **s: policy.suggest(Situation(**s), OPTIONS, near)
    gfast4 = {"gfast": {"positive": True}}
    assert pick(alerts=frozenset({"stroke"}), scores=gfast4)["id"] == "SLH"       # every CSC over 45 min: closest PSC
    assert pick(alerts=frozenset({"stroke"}), scores=gfast4)["cite"].startswith("602 §VI.E.1.c")
    assert pick(scores={"stemi_700a08": {"met": True}})["id"] == "OCH"            # not SLH: not a STEMI center
    trauma = {"trauma_605": {"met": True}}
    assert pick(scores=trauma, values={"patient.age": 40})["id"] == "VMC"         # closest adult trauma center
    assert pick(scores=trauma, values={"patient.age": 8})["rule"] == "trauma_pediatric"
    assert pick(scores=trauma, values={"patient.pregnancy_weeks": 30})["id"] in ("SUH", "VMC")
    assert pick()["id"] == "SLH" and pick()["rule"] == "routine"                  # closest emergency department
    assert DestinationPolicy(CountyRegistry("generic").active).suggest(Situation(), [], near) is None


def test_no_suggestion_once_a_destination_is_set_or_the_patient_has_arrived():
    client, ctx = client_with()
    assert transport(client)["suggestion"]["basis"] == "policy"
    h = {"X-Herald-Patient": ctx.incident.id}
    client.post("/api/transport/destination", json={"facility": "VMC"}, headers=h)
    t = transport(client)
    assert t["suggestion"] is None and t["destination"]["how"] == "chosen"
    client2, ctx2 = client_with()
    client2.post("/api/encounters/current/arrive", headers={"X-Herald-Patient": ctx2.incident.id})
    assert transport(client2)["suggestion"] is None


def test_the_medics_tap_replaces_a_heard_value_which_stays_in_the_record():
    client, ctx = client_with()
    said = say(ctx.incident, "Good Sam", role=Role.family, captured_by=CapturedBy.other)
    h = {"X-Herald-Patient": ctx.incident.id}
    assert client.post("/api/transport/destination", json={"facility": "GSH"}, headers=h).status_code == 200
    now = ctx.incident.latest("transport.destination")
    assert now.value == "Good Samaritan Hospital" and now.status == Status.confirmed
    assert next(f for f in ctx.incident.facts if f.id == said.id).status == Status.rejected   # kept, not deleted
    assert client.post("/api/transport/destination", json={"facility": "XYZ"}, headers=h).status_code == 404
    stale = {"X-Herald-Patient": "someone-else"}
    assert client.post("/api/transport/destination", json={"facility": "RSJ"}, headers=stale).status_code == 409


def test_what_depends_on_the_destination_follows_a_heard_one():
    client, ctx = make_client(ed_url="http://127.0.0.1:8200", ed_receivers={"RSJ": "http://127.0.0.1:8201"})
    ctx.transport.resolver = DestinationResolver(Chooser("RSJ"))
    say(ctx.incident, "Regional")
    run_match(ctx)
    assert ctx.receiver_for("Regional Medical Center of San Jose") == "http://127.0.0.1:8201"
    h = {"X-Herald-Patient": ctx.incident.id}
    client.post("/api/relay/authorize", json={"destination": "Regional Medical Center of San Jose"}, headers=h)
    assert ctx.relay.ed_url == "http://127.0.0.1:8201"
    client.post("/api/encounters/current/handover", json={}, headers=h)
    assert ctx.incident.handed_over_to == "Regional Medical Center of San Jose"
