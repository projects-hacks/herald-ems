"""E1: the one decision point every outbound HTTP call passes through (herald/egress/policy.py)."""
from __future__ import annotations

import httpx
import pytest

from fakes import make_client
from herald.egress import EgressPolicy, host_of


def test_local_model_endpoint_is_always_allowed_and_never_counted_as_cloud():
    policy = EgressPolicy(ed_allow_list=[])
    d = policy.decide("http://127.0.0.1:8080/v1/chat/completions", purpose="model:chat")
    assert d.action == "allow" and d.counted_cloud is False
    assert policy.snapshot()["cloud_ai_calls"] == 0
    assert policy.counts["allow_local"] == 1


def test_allow_listed_ed_host_is_allowed_on_a_good_link_and_queued_when_down():
    policy = EgressPolicy(ed_allow_list=["ed.example.org:8200"])
    good = policy.decide("http://ed.example.org:8200/ingest", purpose="relay:packet", link_state="good")
    assert good.action == "allow" and good.counted_cloud is False
    down = policy.decide("http://ed.example.org:8200/ingest", purpose="relay:packet", link_state="down")
    assert down.action == "queue" and down.counted_cloud is False


def test_unlisted_non_local_host_is_denied_and_counted_as_a_refused_cloud_call():
    policy = EgressPolicy(ed_allow_list=["ed.example.org"])
    d = policy.decide("https://some-cloud-llm.example.com/v1/chat/completions", purpose="model:chat")
    assert d.action == "deny" and d.counted_cloud is True
    snap = policy.snapshot()
    assert snap["cloud_ai_calls"] == 0          # no cloud call is ever actually made: it was refused before it happened
    assert snap["cloud_calls_refused"] == 1


def test_decision_log_is_bounded():
    policy = EgressPolicy(ed_allow_list=[], decision_log_size=3)
    for _ in range(10):
        policy.decide("https://not-allowed.example.com")
    assert len(policy.log) == 3
    assert policy.counts["deny"] == 10          # counters keep the full history; the log is a bounded window


def test_host_of_handles_bare_host_host_port_and_full_urls():
    assert host_of("127.0.0.1") == "127.0.0.1"
    assert host_of("ed.example.org:8200") == "ed.example.org"
    assert host_of("http://ed.example.org:8200/ingest") == "ed.example.org"
    assert host_of("") == ""


def test_relay_config_rejects_a_non_local_non_allow_listed_ed_url():
    c, ctx = make_client()
    r = c.post("/api/relay/config", json={"ed_url": "http://not-allow-listed.example.com"})
    assert r.status_code == 403
    assert "egress policy" in r.json()["detail"]
    assert ctx.relay.ed_url is None                # never stored: the denial happens before `set_ed_url`


def test_relay_config_accepts_an_allow_listed_ed_url():
    c, ctx = make_client()
    ctx.egress.allow_hosts.add("ed-allowed")
    r = c.post("/api/relay/config", json={"ed_url": "http://ed-allowed"})
    assert r.status_code == 200
    assert ctx.relay.ed_url == "http://ed-allowed"


def test_get_egress_reports_counts_and_a_recent_log():
    c, ctx = make_client()
    ctx.egress.decide("http://127.0.0.1:8080/v1", purpose="model:chat")
    ctx.egress.decide("https://denied.example.com", purpose="test")
    r = c.get("/api/egress")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["allow_local"] >= 1
    assert body["counts"]["deny"] >= 1
    assert body["cloud_ai_calls"] == 0
    assert body["cloud_calls_refused"] >= 1
    assert any(row["host"] == "denied.example.com" for row in body["log"])


def test_protocol_sync_denies_a_non_allow_listed_mirror_and_queues_when_the_link_is_down(tmp_path):
    import copy

    from herald.knowledge import KnowledgeBase, ProtocolSync
    from test_knowledge import COUNTY

    county = copy.deepcopy(COUNTY)
    county["documents"] = [d for d in county["documents"] if d["id"] == "700-A13"]
    county["documents"][0]["mirror_url"] = "http://not-allow-listed.example.com/700-A13.pdf"
    kb = KnowledgeBase(county, tmp_path)   # no local copy of the document: `document_path` is None, harmless here

    calls = []

    def fetch(url, headers):
        calls.append(url)
        return httpx.Response(200, content=b"%PDF-1.4")

    policy = EgressPolicy(ed_allow_list=[])
    sync = ProtocolSync(lambda: kb, lambda: "good",
                        {"sync": {"interval_s": 0, "only_when_link": None, "timeout_s": 5}},
                        fetch=fetch, egress=policy)
    result = sync.run(force=True)
    assert calls == []                              # the fetch never happens: denied before it's called
    assert result["errors"] and "egress policy denied" in result["errors"][0]["error"]

    policy2 = EgressPolicy(ed_allow_list=["not-allow-listed.example.com"])
    sync2 = ProtocolSync(lambda: kb, lambda: "down",
                         {"sync": {"interval_s": 0, "only_when_link": None, "timeout_s": 5}},
                         fetch=fetch, egress=policy2)
    result2 = sync2.run(force=True)
    assert calls == []                              # allow-listed, but queued because the link is down
    assert result2["errors"] == [] and result2["updated"] == []
