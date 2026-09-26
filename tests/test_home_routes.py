"""The landing page is the homepage and the medic dashboard lives at /app/ (owner, 2026-09-26)."""
import pytest

from fakes import make_client


def test_home_is_the_landing_page_and_the_dashboard_is_at_app():
    client, ctx = make_client()
    dist = ctx.settings.root / "ui" / "dist"
    if not (dist / "landing" / "index.html").exists() or ctx.settings.ui != "new":
        pytest.skip("no built UI in this checkout")
    home = client.get("/")
    assert home.status_code == 200 and home.text == (dist / "landing" / "index.html").read_text()
    app = client.get("/app/?fixture=stroke_demo")
    assert app.status_code == 200 and app.text == (dist / "index.html").read_text()
    moved = client.get("/app?fixture=stroke_demo", follow_redirects=False)
    assert moved.status_code == 307 and moved.headers["location"] == "/app/?fixture=stroke_demo"
    assert client.get("/monitor.html").status_code == 200                  # the simulator stays where it was


def test_open_herald_starts_a_fresh_patient_case_and_keeps_the_last_one():
    # the last case keeps its record in the encounter history (an untouched empty one does not: test below)
    client, ctx = make_client()
    dist = ctx.settings.root / "ui" / "dist"
    if not (dist / "landing" / "index.html").exists() or ctx.settings.ui != "new":
        pytest.skip("no built UI in this checkout")
    before = ctx.incident.id
    client.post("/api/transcript", json={"text": "Pulse ninety five.", "captured_by": "medic", "use_llm": False})
    moved = client.get("/app/new?dispatch=chest%20pain", follow_redirects=False)
    assert moved.status_code == 303 and moved.headers["location"] == "/app/"
    assert ctx.incident.id != before and ctx.incident.dispatch == "chest pain"
    assert any(row["id"] == before for row in client.get("/api/encounters").json()["encounters"])


def test_a_case_left_empty_is_not_kept_as_an_encounter():
    # "Open Herald" starts a fresh case each time; an untouched one before it is not an encounter
    client, ctx = make_client()
    with client:
        client.get("/app/new", follow_redirects=False)
        client.get("/app/new", follow_redirects=False)
        assert client.get("/api/encounters").json()["encounters"] == []
        client.post("/api/transcript", json={"text": "Pulse ninety five.", "captured_by": "medic", "use_llm": False})
        client.get("/app/new", follow_redirects=False)
        assert len(client.get("/api/encounters").json()["encounters"]) == 1
