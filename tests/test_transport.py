"""Destination, road ETA and how an encounter ended: the county list, the vehicle's position, the medic's taps."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from fakes import FakeModel, make_client
from herald.config import Settings, load_yaml
from herald.config.county import CountyRegistry
from herald.core.schema import CapturedBy, FactIn, Role, Status
from herald.transport import DestinationResolver, OsrmRouter, TransportService, facilities

COUNTY = CountyRegistry("santa_clara").active
CFG = {"position_stale_s": 120, "recompute_moved_m": 75, "recompute_every_s": 30, "max_accuracy_m": 500}
DOWNTOWN = (37.3382, -121.8863)


class FakeRouter:
    """Drive time grows with the facility's index, so the nearest-first order is known."""
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    async def table(self, origin, destinations):
        self.calls += 1
        if self.fail:
            raise httpx.ConnectError("router down")
        return [(600.0 + 60 * i, 8000.0 + 1000 * i) for i in range(len(destinations))]


class Chooser:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat_json(self, system, user, **kw):
        self.calls.append((user, kw["schema"]))
        return self.reply


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 26, 1, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def service(router=None, resolver=None, clock=None):
    return TransportService(lambda: COUNTY, router, resolver, CFG, clock or Clock())


def heard(inc, value):
    """A destination overheard in the cabin: it waits for the medic."""
    fact = inc.ingest(FactIn(key="transport.destination", value=value, role=Role.family, captured_by=CapturedBy.other))
    assert fact.status == Status.unconfirmed
    return fact


def confirmed(inc, key, value):
    return inc.set_status(inc.ingest(FactIn(key=key, value=value)).id, Status.confirmed)


# ---------- the county's hospitals ----------
def test_every_santa_clara_hospital_has_a_route_point_and_its_policy_designations():
    rows = {f.id: f for f in facilities(COUNTY)}
    assert len(rows) == 10 and all(f.routable for f in rows.values())
    assert "Comprehensive Stroke Center" in rows["GSH"].designations
    assert rows["VMC"].designations == ("Primary Stroke Center",)
    assert rows["SUH"].point == "emergency entrance"
    assert facilities(CountyRegistry("generic").active) == []


# ---------- a spoken destination ----------
def test_official_name_matches_without_the_model_and_the_model_only_chooses_listed_ids():
    options = facilities(COUNTY)
    model = Chooser({"id": "GSH"})
    r = DestinationResolver(model)
    assert r.resolve("good samaritan hospital", options) == "GSH" and not model.calls
    assert r.resolve("Good Sam", options) == "GSH"
    assert model.calls[0][1]["properties"]["id"]["enum"][-1] == "none"      # it may always say none
    assert DestinationResolver(Chooser({"id": "none"})).resolve("Kaiser", options) is None
    assert DestinationResolver(Chooser({"id": "MADE-UP"})).resolve("somewhere", options) is None


def test_heard_destination_is_matched_off_the_request_path_and_only_suggested():
    client, ctx = make_client()
    ctx.transport.resolver = DestinationResolver(Chooser({"id": "GSH"}))
    heard(ctx.incident, "Good Sam")
    [text] = ctx.transport.pending_matches(ctx.incident)
    assert ctx.transport.pending_matches(ctx.incident) == []                   # one lookup at a time
    ctx.transport.match(text)
    d = client.get("/api/state").json()["transport"]["destination"]
    assert d == {**d, "status": "unconfirmed", "id": None, "suggested": "GSH", "value": "Good Sam"}
    assert ctx.incident.latest("transport.destination", confirmed_only=True) is None


# ---------- the medic's tap ----------
def test_tapping_a_hospital_confirms_it_and_retires_the_heard_value():
    client, ctx = make_client()
    said = heard(ctx.incident, "Good Sam")
    h = {"X-Herald-Patient": ctx.incident.id}
    assert client.post("/api/transport/destination", json={"facility": "GSH"}, headers=h).status_code == 200
    now = ctx.incident.latest("transport.destination")
    assert now.value == "Good Samaritan Hospital" and now.status == Status.confirmed
    assert next(f for f in ctx.incident.facts if f.id == said.id).status == Status.rejected   # kept, not deleted
    assert client.post("/api/transport/destination", json={"facility": "XYZ"}, headers=h).status_code == 404
    stale = {"X-Herald-Patient": "someone-else"}
    assert client.post("/api/transport/destination", json={"facility": "RSJ"}, headers=stale).status_code == 409


# ---------- position and road ETA ----------
def test_drive_times_come_nearest_first_and_the_eta_follows_the_route_while_the_position_is_fresh():
    client, ctx = make_client()
    clock = Clock()
    ctx.transport = TransportService(lambda: COUNTY, FakeRouter(), None, CFG, clock)
    confirmed(ctx.incident, "transport.eta_min", 25)
    confirmed(ctx.incident, "transport.destination", "Regional Medical Center of San Jose")
    asyncio.run(ctx.transport.update_position(*DOWNTOWN, 12.0, clock.now))
    view = ctx.transport.view(ctx.incident, None, clock.now)
    assert [o["minutes"] for o in view["options"]][:3] == [10, 11, 12] and view["position"]["fresh"]
    assert view["eta"]["source"] == "route"
    arrive = ctx.transport.arrival(ctx.incident, clock.now)
    rsj = next(o for o in view["options"] if o["id"] == "RSJ")
    assert arrive == clock.now + timedelta(minutes=rsj["minutes"])
    clock.now += timedelta(seconds=121)                                         # the tablet stopped reporting
    crew = {"until": "2026-09-26T01:25:00+00:00"}
    later = ctx.transport.view(ctx.incident, crew, clock.now)
    assert later["eta"] == {"source": "crew", "until": crew["until"]} and all(o["minutes"] is None for o in later["options"])


def test_a_small_move_reuses_the_route_and_an_imprecise_fix_is_not_routed():
    clock, router = Clock(), FakeRouter()
    t = service(router, clock=clock)
    asyncio.run(t.update_position(*DOWNTOWN, 10.0))
    asyncio.run(t.update_position(DOWNTOWN[0] + 0.0001, DOWNTOWN[1], 10.0))   # ~11 m
    assert router.calls == 1
    clock.now += timedelta(seconds=31)
    asyncio.run(t.update_position(*DOWNTOWN, 10.0))
    assert router.calls == 2
    asyncio.run(t.update_position(37.40, -121.90, 2000.0))                     # Wi-Fi guess: kept, not routed
    assert router.calls == 2 and t.position["accuracy_m"] == 2000.0


def test_a_router_failure_is_reported_and_leaves_the_crew_estimate():
    t = service(FakeRouter(fail=True))
    asyncio.run(t.update_position(*DOWNTOWN, 10.0))
    view = t.view(_Inc(), {"until": "x"})
    assert view["router_error"] == "ConnectError" and view["eta"] == {"source": "crew", "until": "x"}
    with pytest.raises(ValueError):
        asyncio.run(t.update_position(95.0, 0.0, 1.0))


class _Inc:
    def latest(self, key, confirmed_only=False):
        return None


def test_position_endpoint_and_snapshot_eta_clock_say_their_source():
    client, ctx = make_client()
    ctx.transport.router = FakeRouter()
    confirmed(ctx.incident, "transport.destination", "Good Samaritan Hospital")
    assert client.post("/api/transport/position", json={"lat": DOWNTOWN[0], "lon": DOWNTOWN[1], "accuracy_m": 8}).json() == {"ok": True}
    assert client.post("/api/transport/position", json={"lat": 91, "lon": 0}).status_code == 422
    snap = client.get("/api/state").json()
    [eta] = [c for c in snap["clocks"] if c["id"] == "eta"]
    assert eta["source"] == "route" and snap["transport"]["destination"]["id"] == "GSH"


def test_osrm_adapter_reads_the_table_response():
    def handler(request):
        assert request.url.path.startswith("/table/v1/driving/-121.886300,37.338200;")
        return httpx.Response(200, json={"code": "Ok", "durations": [[0, 600.5, None]], "distances": [[0, 8000, None]]})
    router = OsrmRouter("http://127.0.0.1:5100", transport=httpx.MockTransport(handler))
    assert asyncio.run(router.table(DOWNTOWN, [(37.25, -121.94), (0.0, 0.0)])) == [(600.5, 8000.0), None]


def test_the_router_must_be_on_this_box():
    with pytest.raises(ValueError):
        Settings(routing_url="http://maps.example.com:5000")
    assert Settings(routing_url="http://127.0.0.1:5100").routing_url


# ---------- what the ED gets ----------
def test_ed_gets_the_route_arrival_time_only_where_arrival_logistics_are_authorized():
    client, ctx = make_client()
    ctx.transport.router = FakeRouter()
    confirmed(ctx.incident, "transport.destination", "Good Samaritan Hospital")
    asyncio.run(ctx.transport.update_position(*DOWNTOWN, 8.0))
    ctx.relay.authorize("Good Samaritan Hospital", "patient update set", ())
    values = ctx.relay.critical_values(ctx.incident)
    assert values["transport.eta_at"].endswith(":00+00:00")                  # whole minutes: no resend every fix
    ctx.relay.authorize("Good Samaritan Hospital", "Stroke alert pre-alert set", ("stroke",))
    assert "transport.eta_at" not in ctx.relay.critical_values(ctx.incident)   # config/relay.yaml consent ceiling


def test_each_hospital_can_have_its_own_receiver():
    client, ctx = make_client(ed_url="http://127.0.0.1:8200", ed_receivers={"GSH": "http://127.0.0.1:8201"})
    confirmed(ctx.incident, "transport.destination", "Good Samaritan Hospital")
    client.post("/api/relay/authorize", json={"destination": "Good Samaritan Hospital"}, headers={"X-Herald-Patient": ctx.incident.id})
    assert ctx.relay.ed_url == "http://127.0.0.1:8201"
    assert ctx.egress.decide("http://127.0.0.1:8201/ingest", purpose="relay").action != "deny"


# ---------- how the encounter ended ----------
def test_finishing_needs_an_outcome_and_a_refusal_tells_an_alerted_ed_the_patient_is_not_coming():
    client, ctx = make_client()
    h = {"X-Herald-Patient": ctx.incident.id}
    assert client.post("/api/encounters/current/finish", headers=h).status_code == 422
    assert client.post("/api/encounters/current/finish", json={"disposition": "gone"}, headers=h).status_code == 422
    ctx.relay.authorize("Regional", "patient update set", ())
    inc = ctx.incident
    done = client.post("/api/encounters/current/finish", json={"disposition": "refused"}, headers=h).json()
    assert done["incident"]["disposition"] == "refused" and any(a.get("action") == "disposition" for a in inc.audit_log)
    assert ctx.relay.critical_values(inc)["encounter.disposition"] == "Patient refused transport"


def test_a_transported_patient_cannot_be_finished_as_not_transported():
    client, ctx = make_client()
    h = {"X-Herald-Patient": ctx.incident.id}
    client.post("/api/encounters/current/arrive", headers=h)
    assert client.post("/api/encounters/current/finish", json={"disposition": "refused"}, headers=h).status_code == 409
    ok = client.post("/api/encounters/current/finish", json={"disposition": "transported"}, headers=h).json()
    assert ok["incident"]["disposition"] == "transported"
    assert "encounter.disposition" not in ctx.relay.critical_values(ctx.incident)


def test_outcomes_carry_verified_nemsis_codes_and_reach_the_ui_contract():
    outcomes = load_yaml("dispositions.yaml")["outcomes"]
    assert [o["id"] for o in outcomes if o["transport"]] == ["transported"]
    assert {o["nemsis"]["transport"] for o in outcomes} <= {"4230001", "4230005", "4230009", "4230013", "7701001"}
    client, _ = make_client()
    meta = client.get("/api/meta").json()
    assert meta["dispositions"] == outcomes and meta["derived_labels"]["transport.eta_at"]


def test_the_outcome_survives_a_restart(tmp_path):
    client, ctx = make_client(data_dir=tmp_path / "data", state_key_file=tmp_path / "k" / "key", persistence=True)
    h = {"X-Herald-Patient": ctx.incident.id}
    client.post("/api/encounters/current/finish", json={"disposition": "not_transported"}, headers=h)
    again, ctx2 = make_client(data_dir=tmp_path / "data", state_key_file=tmp_path / "k" / "key", persistence=True)
    assert ctx2.incident.disposition == "not_transported"


def test_hand_over_is_a_transport_by_this_unit():
    client, ctx = make_client()
    h = {"X-Herald-Patient": ctx.incident.id}
    inc = ctx.incident
    client.post("/api/encounters/current/handover", json={"destination": "Good Samaritan Hospital"}, headers=h)
    assert inc.disposition == "transported" and inc.handed_over_at
    assert "encounter.disposition" not in ctx.relay.critical_values(inc)
