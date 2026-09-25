"""/api/health `memory` block (herald/telemetry/memory.py), the memory-guard settings and the STT preload."""
import json
import time

import pytest
from fakes import make_client

from herald.api.app import preload_stt
from herald.config.settings import Settings
from herald.telemetry.memory import guard_state, memory_health, parse_meminfo

MEMINFO = "MemTotal:       127535340 kB\nMemFree:        70000000 kB\nMemAvailable:    94371840 kB\n"


def test_parse_meminfo():
    assert parse_meminfo(MEMINFO) == {"available_gib": 90.0, "total_gib": 121.6}
    assert parse_meminfo("MemTotal: 1048576 kB\n") == {"available_gib": None, "total_gib": 1.0}


@pytest.mark.parametrize("status, now, running", [
    ({"ts": 100.0, "mode": "demo", "last_action": {"event": "kill"}}, 102.0, True),
    ({"ts": 100.0, "mode": "normal"}, 106.0, False),              # stale heartbeat
    ({"ts": "x"}, 100.0, False),
    (None, 100.0, False),                                         # missing or corrupt file
    ([], 100.0, False),
])
def test_guard_state(status, now, running):
    g = guard_state(status, now, 5.0)
    assert g["running"] is running
    if isinstance(status, dict) and "mode" in status:
        assert g["mode"] == status["mode"]


def test_memory_health_files(tmp_path):
    mi = tmp_path / "meminfo"
    mi.write_text(MEMINFO)
    st = tmp_path / "memguard.json"
    st.write_text(json.dumps({"ts": 50.0, "mode": "demo", "last_action": {"event": "victim_gone"}}))
    got = memory_health(st, 5.0, meminfo_path=str(mi), now=52.0)
    assert got == {"available_gib": 90.0, "total_gib": 121.6,
                   "guard": {"running": True, "mode": "demo", "last_action": {"event": "victim_gone"}}}
    st.write_text("{not json")
    assert memory_health(st, 5.0, meminfo_path=str(mi), now=52.0)["guard"] == \
        {"running": False, "mode": None, "last_action": None}
    assert memory_health(tmp_path / "missing.json", 5.0, meminfo_path=str(mi))["guard"]["running"] is False


def test_settings_env():
    s = Settings.from_env({"HERALD_STT_PRELOAD": "1", "HERALD_MEMGUARD_STATUS": "/tmp/x.json",
                           "HERALD_MEMGUARD_STALE_S": "9"})
    assert s.stt_preload is True and str(s.memguard_status) == "/tmp/x.json" and s.memguard_stale_s == 9.0
    d = Settings.from_env({})
    assert d.stt_preload is False and d.memguard_status.name == "memguard.json" and d.memguard_stale_s == 5.0


def test_health_has_memory_block(tmp_path):
    st = tmp_path / "memguard.json"
    st.write_text(json.dumps({"ts": time.time(), "mode": "normal", "last_action": None}))
    c, _ = make_client(memguard_status=st)
    mem = c.get("/api/health").json()["memory"]
    assert mem["total_gib"] > 0 and 0 <= mem["available_gib"] <= mem["total_gib"]
    assert mem["guard"] == {"running": True, "mode": "normal", "last_action": None}


class _STT:
    def __init__(self, fail=False):
        self.fail, self.loaded = fail, False

    def warm(self):
        if self.fail:
            raise OSError("weights not found")
        self.loaded = True

    def ready(self):
        return self.loaded


def test_preload_loads_or_fails_loudly():
    s = _STT()
    preload_stt(s)
    assert s.ready()
    with pytest.raises(RuntimeError, match="failed to load: OSError: weights not found"):
        preload_stt(_STT(fail=True))


def test_app_startup_preloads(tmp_path):
    c, ctx = make_client(stt_preload=True, memguard_status=tmp_path / "none.json")
    with c:                                                   # runs the lifespan
        assert c.get("/api/health").json()["stt_loaded"] is True
