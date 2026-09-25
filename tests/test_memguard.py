"""Memory guard (scripts/memguard/): config loading and validation, levels, protection, victim classes and order,
demo-mode rules, parsers, and the terminator on real child processes."""
import copy
import subprocess
import sys
import time

import pytest
import yaml

from scripts.memguard import config as mgconfig, policy, probe
from scripts.memguard.actions import Terminator, wait_gone
from scripts.memguard.probe import Proc

UID = 1000
CFG = mgconfig.load()


def P(pid, ppid, cmd, rss_gib=0.0, uid=UID, exe=None, cgroup="/user.slice/user-1000.slice/session-2.scope",
      start=1000.0):
    return Proc(pid, ppid, uid, int(rss_gib * 1024 ** 2), start, cmd, exe or cmd.split()[0], cgroup)


JOB_CG = "/user.slice/user-1000.slice/user@1000.service/app.slice/herald-job-train-20260924T220000.scope"


def table():
    procs = [
        P(1, 0, "/sbin/init", uid=0),
        P(10, 1, "/usr/lib/systemd/systemd --user"),
        P(20, 10, "/snap/zrt/9/bin/zrt __proxy start --mode system", 0.1),
        P(30, 1, "/opt/hp/zrt/venv/bin/python /opt/hp/zrt/venv/bin/vllm serve /m --served-model-name ems-e-v2-fp8",
          1.3),
        P(31, 30, "VLLM::EngineCore", 2.6, exe="/opt/hp/zrt/venv/bin/python"),
        P(40, 1, "/opt/hp/zrt/venv/bin/python /opt/hp/zrt/venv/bin/vllm serve /m --served-model-name omni", 1.0),
        P(41, 40, "VLLM::EngineCore", 2.0, exe="/opt/hp/zrt/venv/bin/python"),
        P(50, 1, "/home/hp18/miniforge3/envs/zgx/bin/python -m uvicorn herald.app:app --port 8100", 6.0),
        P(51, 50, "ffmpeg -i x", 0.2),
        P(60, 1, "/bin/bash -c something"),
        P(61, 60, "/home/hp18/miniforge3/envs/zgx/bin/python scripts/asr_layer.py transcribe", 3.0),
        P(70, 60, "/home/hp18/.venvs/piper/bin/python scripts/asr_tts.py --workers 2", 0.3),
        P(71, 70, "/home/hp18/.venvs/piper/bin/python scripts/asr_tts.py --workers 2", 2.5,
          exe="/home/hp18/.venvs/piper/bin/python"),
        P(72, 70, "/home/hp18/.venvs/piper/bin/python scripts/asr_tts.py --workers 2", 2.5,
          exe="/home/hp18/.venvs/piper/bin/python"),
        P(80, 1, "/bin/bash -c python train.py", 0.01, cgroup=JOB_CG),
        P(81, 80, "/home/hp18/miniforge3/envs/zgx/bin/python train.py", 1.0, cgroup=JOB_CG),
        P(90, 1, "/home/hp18/.vscode-server/cli/servers/x/server/node", 0.6),
        P(95, 1, "/home/hp18/miniforge3/envs/zgx/bin/python scripts/memguard.py run", 0.04),
        P(99, 1, "/usr/bin/python3 someone_elses_job.py", 20.0, uid=1001),
    ]
    return {p.pid: p for p in procs}


GPU = {31: 12_000.0, 41: 30_000.0, 61: 4_000.0, 81: 20_000.0, 50: 3_000.0}


def classify(procs=None, gpu=None, cfg=CFG, owners=(50,)):
    return policy.classify(procs or table(), GPU if gpu is None else gpu, cfg, uid=UID, self_pid=95,
                           port_owner_pids=owners)


# ---- config
def test_config_loads_and_is_consistent():
    assert CFG.thresholds.kill_below_gib < CFG.thresholds.warn_below_gib
    assert CFG.demo.thresholds.kill_below_gib >= CFG.thresholds.kill_below_gib
    assert CFG.victims == ("guarded_jobs", "user_processes", "vllm_services", "critical_jobs")
    assert CFG.critical_term_grace_s >= 5 * CFG.term_grace_s
    assert "ems-e-v2-fp8" in CFG.protected.vllm_keep and 8100 in CFG.protected.ports
    assert CFG.run_job.oom_score_adj == 1000 and CFG.run_job.unit_prefix == "herald-job-"


def _raw():
    with open(mgconfig.DEFAULT_CONFIG) as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("mutate, msg", [
    (lambda r: r["thresholds"].update(kill_below_gib=20), "kill_below_gib must be below"),
    (lambda r: r["thresholds"].pop("warn_below_gib"), "missing thresholds.warn_below_gib"),
    (lambda r: r["thresholds"].update(psi_full_avg10_kill=250), "percentage"),
    (lambda r: r.update(poll_hz=0), "poll_hz must be > 0"),
    (lambda r: r.update(victims=["guarded_jobs", "everyone"]), "victims"),
    (lambda r: r.update(victims=["guarded_jobs", "guarded_jobs"]), "victims"),
    (lambda r: r["protected"]["rules"].append({"name": "bad", "cmdline": "("}), "bad regex"),
    (lambda r: r["protected"].update(ports=[70000]), "TCP ports"),
    (lambda r: r["run_job"].update(oom_score_adj=-500), "oom_score_adj"),
    (lambda r: r["demo"].pop("thresholds"), "missing demo.thresholds"),
])
def test_config_validation(mutate, msg):
    raw = copy.deepcopy(_raw())
    mutate(raw)
    with pytest.raises(mgconfig.ConfigError, match=msg):
        mgconfig.parse(raw)


def test_paths_expand_home(tmp_path):
    cfg = mgconfig.parse(_raw(), home=tmp_path)
    assert cfg.paths.status_file == tmp_path / ".local/state/herald/memguard.json"
    assert cfg.paths.gpu_lock == tmp_path / ".cache/herald-gpu.lock"


# ---- levels
@pytest.mark.parametrize("avail, psi_full, level", [
    (90, 0, "ok"), (16.0, 0, "ok"), (15.9, 0, "warn"), (8.0, 0, "warn"), (7.9, 0, "kill"),
    (90, 25.0, "ok"), (90, 25.1, "kill"), (12, 30, "kill"),
])
def test_levels(avail, psi_full, level):
    assert policy.evaluate(avail, psi_full, CFG.thresholds).name == level


def test_demo_thresholds_are_stricter():
    assert policy.evaluate(11.0, 0, CFG.thresholds_for(True)).name == "kill"
    assert policy.evaluate(11.0, 0, CFG.thresholds_for(False)).name == "warn"


# ---- protection and classes
def test_protected_never_victims():
    c = classify()
    victim_pids = {p for v in c.victims for p in v.pids}
    for pid in (10, 20, 30, 31, 50, 51, 60, 90, 95):
        assert pid in c.protected, pid
        assert pid not in victim_pids, pid
    assert 99 not in victim_pids and 99 not in c.protected          # other users are never touched
    assert c.protected[31].startswith("vLLM keep-list")
    assert c.protected[50] == "demo port" and c.protected[51] == "demo port"


def test_classes():
    by = {v.root: v for v in classify().victims}
    assert by[80].klass == "guarded_jobs" and set(by[80].pids) == {80, 81}   # whole scope, even the bash
    assert by[80].unit.startswith("herald-job-train-")
    assert by[40].klass == "vllm_services" and by[40].service == "omni" and set(by[40].pids) == {40, 41}
    assert by[61].klass == "user_processes"
    assert set(by[70].pids) == {70, 71, 72}                                  # a worker pool is one group
    assert by[81 - 1].gpu_gib == pytest.approx(20_000 / 1024)


def test_order_class_first_then_largest():
    ranked = policy.order(classify().victims, CFG)
    assert [v.root for v in ranked] == [80, 61, 70, 40]   # asr 3.0+3.9 GiB > pool 5.3 GiB
    assert ranked[0].klass == "guarded_jobs"
    sizes = [v.size_gib for v in ranked if v.klass == "user_processes"]
    assert sizes == sorted(sizes, reverse=True)


def test_order_drops_tiny_groups():
    procs = table()
    procs[61] = P(61, 60, "/home/hp18/miniforge3/envs/zgx/bin/python tiny.py", 0.1)
    ranked = policy.order(classify(procs, gpu={}).victims, CFG)
    assert 61 not in [v.root for v in ranked]


def test_keep_list_change_moves_service_to_class_c():
    raw = copy.deepcopy(_raw())
    raw["protected"]["vllm_keep"] = []
    cfg = mgconfig.parse(raw)
    by = {v.root: v for v in classify(cfg=cfg).victims}
    assert by[30].klass == "vllm_services" and by[30].service == "ems-e-v2-fp8"


def test_choose_none_when_only_protected():
    procs = {k: v for k, v in table().items() if k in (1, 10, 20, 30, 31, 50, 51, 90, 95)}
    assert policy.choose(classify(procs), CFG) is None


def test_job_unit_parsing():
    assert policy.job_unit(JOB_CG, "herald-job-") == "herald-job-train-20260924T220000.scope"
    assert policy.job_unit("/user.slice/x/session-2.scope", "herald-job-") is None


def test_served_label():
    assert policy.served_label("/v/bin/vllm serve /m --served-model-name herald-f --x 1") == "herald-f"
    assert policy.served_label("python train.py --served-model-name x") is None


# ---- demo mode
def test_demo_strangers_only_new_gpu_holders():
    procs = table()
    procs[61] = P(61, 60, "/home/hp18/miniforge3/envs/zgx/bin/python scripts/asr_layer.py", 3.0, start=2000.0)
    c = classify(procs)
    strangers = policy.demo_strangers(c, GPU, procs, CFG, demo_since=1500.0)
    assert [v.root for v in strangers] == [61]                      # started after demo mode, holds GPU memory
    assert policy.demo_strangers(c, GPU, procs, CFG, demo_since=3000.0) == []
    assert all(50 not in v.pids for v in strangers)                 # the demo app holds GPU but is protected


# ---- parsers
def test_parse_meminfo_and_psi():
    m = probe.parse_meminfo("MemTotal:       127535340 kB\nMemAvailable:    94371840 kB\nHugePages_Total: 0\n")
    assert m["MemAvailable"] == 94371840 * 1024 and m["HugePages_Total"] == 0
    p = probe.parse_psi("some avg10=1.50 avg60=0.20 avg300=0.00 total=25\nfull avg10=0.75 avg60=0.00 avg300=0.00 "
                        "total=24\n")
    assert p["full_avg10"] == 0.75 and p["some_avg10"] == 1.5


def test_parse_nvidia_smi():
    out = probe.parse_nvidia_smi("4910, VLLM::EngineCore, 12763 MiB\n777, python, 512\n12, x, [N/A]\n\n")
    assert out == {4910: 12763.0, 777: 512.0}


def test_real_probes_work():
    avail, total = probe.available_gib()
    assert 0 < avail <= total
    procs = probe.processes()
    import os
    assert os.getpid() in procs and procs[os.getpid()].rss_kib > 0


# ---- terminator on real children
def _child(code):
    return subprocess.Popen([sys.executable, "-c", code])


def test_terminator_sigterm_then_gone():
    p = _child("import time; time.sleep(60)")
    time.sleep(0.2)
    events = []
    t = Terminator(grace_s=1.0, zrt_timeout_s=5.0, log=lambda e, **k: events.append(e))
    v = policy.Victim("user_processes", "sleep", p.pid, (p.pid,), 0.0, 0.0)
    t.start(v, time.monotonic(), {}, "test")
    p.wait(timeout=5)
    assert wait_gone(t, 5.0) == "gone"
    assert events[0] == "kill" and "victim_gone" in events and "sigkill" not in events


def test_terminator_escalates_to_sigkill():
    p = _child("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); "
               "time.sleep(60)")
    time.sleep(0.3)
    events = []
    t = Terminator(grace_s=0.5, zrt_timeout_s=5.0, log=lambda e, **k: events.append(e))
    t.start(policy.Victim("user_processes", "stubborn", p.pid, (p.pid,), 0.0, 0.0), time.monotonic(), {}, "test")
    deadline = time.monotonic() + 5
    while p.poll() is None and time.monotonic() < deadline:
        t.poll(time.monotonic())
        time.sleep(0.05)
    assert p.returncode == -9
    assert wait_gone(t, 3.0) == "gone" and "sigkill" in events


def test_terminator_skips_recycled_pid():
    p = _child("import time; time.sleep(60)")
    try:
        t = Terminator(grace_s=0.5, zrt_timeout_s=5.0, log=lambda e, **k: None)
        v = policy.Victim("user_processes", "x", p.pid, (p.pid,), 0.0, 0.0)
        t.start(v, time.monotonic(), {p.pid: 12345.0}, "test")         # start time mismatch: not our process
        time.sleep(0.3)
        assert p.poll() is None
    finally:
        p.kill()
        p.wait()


def test_event_log_last_action_survives_restart(tmp_path):
    from scripts.memguard.state import EventLog
    log = EventLog(tmp_path / "g.jsonl", echo=False)
    log("start")
    assert log.last is None
    log("kill", victim={"root": 1})
    log("level", level="ok")
    assert log.last["event"] == "kill"
    assert EventLog(tmp_path / "g.jsonl", echo=False).last["event"] == "kill"


def test_guard_tick_dry_run_writes_status(tmp_path):
    from scripts.memguard.daemon import Guard
    from scripts.memguard.state import EventLog
    raw = _raw()
    avail = probe.available_gib()[0]
    raw["thresholds"].update(kill_below_gib=avail + 50, warn_below_gib=avail + 60)   # force the kill level
    cfg = mgconfig.parse(raw, home=tmp_path)
    g = Guard(cfg, log=EventLog(cfg.paths.log_file, echo=False), dry_run=True)
    st = g.tick()
    assert st["level"] == "kill" and st["mode"] == "normal" and st["dry_run"] is True
    assert (tmp_path / ".local/state/herald/memguard.json").exists()
    assert os_getpid() in st["protected_pids"]


def os_getpid():
    import os
    return os.getpid()



# ---- critical jobs (run_job --priority critical)
CRIT_CG = "/user.slice/user-1000.slice/user@1000.service/app.slice/herald-job-train-f-20260924T230000.scope"


def table_with_critical():
    procs = table()
    procs[85] = P(85, 1, "/home/hp18/miniforge3/envs/zgx/bin/python train_f.py", 3.0, cgroup=CRIT_CG)
    return procs


def test_critical_job_is_last_resort():
    pri = {"herald-job-train-f-20260924T230000.scope": "critical"}
    c = policy.classify(table_with_critical(), {**GPU, 85: 70_000.0}, CFG, uid=UID, self_pid=95,
                        port_owner_pids=(50,), job_priority=pri)
    ranked = policy.order(c.victims, CFG)
    assert [v.klass for v in ranked] == ["guarded_jobs", "user_processes", "user_processes", "vllm_services",
                                         "critical_jobs"]
    assert ranked[-1].root == 85 and ranked[-1].size_gib > ranked[0].size_gib   # the biggest, and still last
    only = {k: v for k, v in table_with_critical().items() if k in (1, 10, 20, 30, 31, 50, 85, 95)}
    c2 = policy.classify(only, GPU, CFG, uid=UID, self_pid=95, port_owner_pids=(50,), job_priority=pri)
    assert policy.choose(c2, CFG).klass == "critical_jobs"                        # nothing else left


def test_unknown_priority_means_normal():
    c = classify(table_with_critical())
    assert {v.root: v.klass for v in c.victims}[85] == "guarded_jobs"


def test_job_scopes():
    assert policy.job_scopes(table_with_critical(), "herald-job-") == {
        "herald-job-train-20260924T220000.scope": 80, "herald-job-train-f-20260924T230000.scope": 85}


def test_growing_reports_who_grows():
    procs = table()
    old = policy.sizes(procs, GPU)
    procs[61] = P(61, 60, "/home/hp18/miniforge3/envs/zgx/bin/python scripts/asr_layer.py transcribe", 5.0)
    procs[77] = P(77, 60, "/home/hp18/miniforge3/envs/zgx/bin/python new.py", 1.0, start=2000.0)
    procs[50] = P(50, 1, "/home/hp18/miniforge3/envs/zgx/bin/python -m uvicorn herald.app:app --port 8100", 6.5)
    c = classify(procs)
    got = policy.growing(old, policy.sizes(procs, GPU), procs, c)
    assert [(g["pid"], g["grew_gib"]) for g in got] == [(61, 2.0), (77, 1.0), (50, 0.5)]
    assert got[0]["owner"] == "user_processes" and got[2]["owner"] == "demo port"


def test_terminator_critical_grace_and_warning():
    p = _child("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)")
    time.sleep(0.3)
    events = []
    t = Terminator(grace_s=0.2, zrt_timeout_s=5.0, log=lambda e, **k: events.append((e, k)), critical_grace_s=1.5)
    t0 = time.monotonic()
    t.start(policy.Victim("critical_jobs", "herald-job-train-f", p.pid, (p.pid,), 0.0, 0.0), t0, {}, "test")
    assert events[0][0] == "critical_kill" and "LAST RESORT" in events[0][1]["msg"]
    while p.poll() is None and time.monotonic() - t0 < 5:
        t.poll(time.monotonic())
        time.sleep(0.05)
    assert p.returncode == -9 and time.monotonic() - t0 >= 1.5                  # SIGKILL only after the long grace
