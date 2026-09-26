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
    client, ctx = make_client()
    dist = ctx.settings.root / "ui" / "dist"
    if not (dist / "landing" / "index.html").exists() or ctx.settings.ui != "new":
        pytest.skip("no built UI in this checkout")
    before = ctx.incident.id
    moved = client.get("/app/new?dispatch=chest%20pain", follow_redirects=False)
    assert moved.status_code == 303 and moved.headers["location"] == "/app/"
    assert ctx.incident.id != before and ctx.incident.dispatch == "chest pain"
    assert any(row["id"] == before for row in client.get("/api/encounters").json()["encounters"])
