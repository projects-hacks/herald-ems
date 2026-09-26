"""The ED "incoming ambulance" board: what the receiver serves it and the config it is laid out from."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from ed_receiver.app import INCIDENTS, LINK, app

WEB = Path(__file__).resolve().parent.parent / "ed_receiver" / "web"


def _client() -> TestClient:
    INCIDENTS.clear(); LINK["last_contact_at"] = None
    return TestClient(app)


def test_board_page_and_every_module_it_loads_are_served():
    client = _client()
    page = client.get("/")
    assert page.status_code == 200 and 'src="/app.js"' in page.text and 'href="/screen.css"' in page.text
    assert client.get("/screen.css").status_code == 200
    assert client.get("/fonts/inter-latin-wght-normal.woff2").status_code == 200
    # Every relative ES module import (app.js -> view/journey/handover.mjs -> view.mjs) resolves to a served file.
    pending, seen = ["app.js"], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        response = client.get(f"/{name}")
        assert response.status_code == 200, name
        assert (WEB / name).exists()
        pending += re.findall(r"from '\./([\w.]+)'", response.text)
    assert {"app.js", "view.mjs", "journey.mjs", "handover.mjs"} <= seen
    # No network dependency on the ED laptop: nothing loads from a CDN.
    for name in ["index.html", "screen.css", *seen]:
        assert "http://" not in (WEB / name).read_text() and "https://" not in (WEB / name).read_text(), name


def test_board_layout_names_only_keys_the_receiver_can_label():
    meta = _client().get("/api/meta").json()
    keys, display = meta["keys"], meta["display"]
    named = [*display["safety"], *display["findings"], *display["scores"], *display["care"],
             *[key for tile in display["vitals"] for key in tile["keys"]],
             *[alert["score"] for alert in display["alerts"] if alert.get("score")],
             *display["header"].values()]
    assert not [key for key in named if key not in keys]
    # Each alert badge matches the relayed readiness line by its checklist's label, and a criteria score's not-met line.
    assert all(alert["readiness_label"] for alert in display["alerts"])
    assert keys["score.stemi_700a08"]["not_met"] == "not met"


def test_received_vitals_carry_the_adult_severity_band_and_it_withdraws_for_a_child():
    client = _client()
    try:
        client.post("/ingest", json={"i": "adult", "q": 1, "tier": "critical", "x": 0,
                                     "f": {"patient.age": 62, "vitals.hr": 140, "vitals.sbp": 85, "vitals.spo2": 97}})
        severity = client.get("/state").json()["incidents"]["adult"]["severity"]
        assert severity["vitals.hr"] == "critical" and severity["vitals.sbp"] == "critical"
        assert "vitals.spo2" not in severity                       # normal gets no colour
        client.post("/ingest", json={"i": "adult", "q": 2, "tier": "critical", "x": 0, "f": {"vitals.hr": 80}})
        assert "vitals.hr" not in client.get("/state").json()["incidents"]["adult"]["severity"]
        client.post("/ingest", json={"i": "child", "q": 1, "tier": "critical", "x": 0,
                                     "f": {"patient.age": 6, "vitals.hr": 140}})
        assert client.get("/state").json()["incidents"]["child"]["severity"] == {}
        # A value the bands cannot read never costs the packet: it is acknowledged and the tile stays neutral.
        odd = {"i": "odd", "q": 1, "tier": "critical", "x": 0,
               "f": {"patient.age": "sixty", "vitals.hr": "fast", "vitals.spo2": {"v": 1}}}
        assert client.post("/ingest", json=odd).json() == {"ack": 1}
        assert "vitals.hr" not in client.get("/state").json()["incidents"]["odd"]["severity"]
    finally:
        INCIDENTS.clear(); LINK["last_contact_at"] = None
