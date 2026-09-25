"""Job launcher (scripts/run_job.py, scripts/memguard/launcher.py): refusal in demo mode, the memory wait, the GPU
lock, the systemd-run command, the job environment and the torch GPU-cap hook."""
import fcntl
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.memguard import config as mgconfig, launcher
from scripts.memguard.launcher import JobSpec, Refused
from scripts.memguard.state import JobRegistry

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg(tmp_path):
    with open(mgconfig.DEFAULT_CONFIG) as f:
        return mgconfig.parse(yaml.safe_load(f), home=tmp_path)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_spec_validation():
    with pytest.raises(ValueError):
        JobSpec("bad name!", 1, ("x",))
    with pytest.raises(ValueError):
        JobSpec("ok", 0, ("x",))
    with pytest.raises(ValueError):
        JobSpec("ok", 1, ())


def test_refuses_in_demo_mode(cfg):
    cfg.paths.demo_flag.parent.mkdir(parents=True, exist_ok=True)
    cfg.paths.demo_flag.write_text("on")
    with pytest.raises(Refused, match="demo mode"):
        launcher.run(JobSpec("x", 1, ("true",)), cfg)


def test_cli_exit_code_in_demo_mode(tmp_path):
    raw = yaml.safe_load(mgconfig.DEFAULT_CONFIG.read_text())
    flag = tmp_path / "demo_mode"
    flag.write_text("on")
    raw["paths"]["demo_flag"] = str(flag)
    c = tmp_path / "mg.yaml"
    c.write_text(yaml.safe_dump(raw))
    r = subprocess.run([sys.executable, str(ROOT / "scripts/run_job.py"), "--name", "t", "--need-gib", "1",
                        "--config", str(c), "--", "true"], capture_output=True, text=True)
    assert r.returncode == 75 and "demo mode" in r.stderr


def test_wait_returns_when_memory_frees():
    clock, seq = Clock(), iter([10.0, 20.0, 40.0])
    got = launcher.wait_for_memory(20, 12, 100, available=lambda: next(seq), demo_on=lambda: False,
                                   clock=clock, sleep=clock.sleep, say=lambda s: None)
    assert got == 40.0 and clock.t == 4.0          # 10 and 20 are < 20 + 12; 40 is enough


def test_wait_times_out():
    clock = Clock()
    with pytest.raises(Refused, match="timed out"):
        launcher.wait_for_memory(50, 12, 10, available=lambda: 30.0, demo_on=lambda: False, clock=clock,
                                 sleep=clock.sleep, say=lambda s: None)


def test_wait_refuses_if_demo_goes_on():
    clock, demo = Clock(), iter([False, True])
    with pytest.raises(Refused, match="demo mode"):
        launcher.wait_for_memory(50, 12, 100, available=lambda: 30.0, demo_on=lambda: next(demo), clock=clock,
                                 sleep=clock.sleep, say=lambda s: None)


def test_scope_argv_and_caps(cfg):
    spec = JobSpec("train", 77, ("python", "train.py"), gpu=True)
    argv = launcher.scope_argv(spec, cfg, "herald-job-train-X")
    assert argv[:4] == ["systemd-run", "--user", "--scope", "--quiet"]
    assert "MemoryMax=82944M" in argv and "MemorySwapMax=0" in argv       # 77 + 4 GiB margin
    assert argv[-3:] == ["--", "python", "train.py"]
    assert launcher.host_cap_gib(JobSpec("t", 2, ("x",), host_max_gib=6), cfg) == 6


def test_job_env():
    env = launcher.job_env(JobSpec("t", 2, ("x",)), {"PYTHONPATH": "/a", "HOME": "/h"})
    assert env["HERALD_JOB"] == "t" and env["HERALD_GPU_MAX_GIB"] == "2"
    assert env["PYTHONPATH"] == f"{launcher.GPUCAP_DIR}{os.pathsep}/a"
    assert launcher.job_env(JobSpec("t", 2, ("x",), gpu_max_gib=3.5), {})["HERALD_GPU_MAX_GIB"] == "3.5"


def test_unit_name(cfg):
    assert launcher.unit_name(JobSpec("bench", 1, ("x",)), cfg).startswith("herald-job-bench-20")


def test_gpu_lock_is_exclusive_and_times_out(tmp_path):
    lock = tmp_path / "gpu.lock"
    fd = launcher.acquire_gpu_lock(lock, 5, "first", say=lambda s: None)
    clock = Clock()
    with pytest.raises(Refused, match="GPU lock"):
        launcher.acquire_gpu_lock(lock, 6, "second", clock=clock, sleep=clock.sleep, say=lambda s: None)
    assert lock.read_text() == "first"
    os.close(fd)
    fd2 = launcher.acquire_gpu_lock(lock, 5, "second", say=lambda s: None)
    with pytest.raises(BlockingIOError):
        fcntl.flock(os.open(lock, os.O_RDWR), fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.close(fd2)


def test_registry(tmp_path):
    reg = JobRegistry(tmp_path / "jobs")
    reg.add("herald-job-a-1", pid=os.getpid(), launcher_pid=os.getpid())
    reg.add("herald-job-b-1", pid=999999999, launcher_pid=999999999)
    assert {j["unit"] for j in reg.all()} == {"herald-job-a-1", "herald-job-b-1"}
    assert [j["unit"] for j in reg.prune()] == ["herald-job-a-1"]
    reg.remove("herald-job-a-1")
    assert reg.all() == []


def test_gpucap_hook_is_inert_without_torch(tmp_path):
    """The hook must not import torch itself or break a plain interpreter."""
    env = dict(os.environ, PYTHONPATH=str(launcher.GPUCAP_DIR), HERALD_GPU_MAX_GIB="2", HERALD_JOB="t")
    r = subprocess.run([sys.executable, "-c", "import sys; print('torch' in sys.modules)"], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "False"



# ---- critical priority
def test_priority_validation_and_env():
    with pytest.raises(ValueError, match="priority"):
        JobSpec("t", 1, ("x",), priority="urgent")
    assert launcher.job_env(JobSpec("t", 1, ("x",), priority="critical"), {})["HERALD_JOB_PRIORITY"] == "critical"


def _critical_registry(tmp_path):
    reg = JobRegistry(tmp_path / "jobs")
    reg.add("herald-job-train-f-1", name="train-f", priority="critical", pid=os.getpid(), launcher_pid=os.getpid())
    reg.add("herald-job-bench-1", name="bench", priority="normal", pid=os.getpid(), launcher_pid=os.getpid())
    return reg


def test_gpu_job_refused_while_critical_runs(tmp_path):
    reg = _critical_registry(tmp_path)
    assert [j["name"] for j in reg.critical()] == ["train-f"]
    assert reg.priorities()["herald-job-train-f-1.scope"] == "critical"
    with pytest.raises(Refused, match="critical job is running: train-f"):
        launcher.check_critical(JobSpec("asr", 6, ("x",), gpu=True), reg, None)
    launcher.check_critical(JobSpec("cpu", 6, ("x",)), reg, None)                  # CPU jobs still run


def test_gpu_job_waits_for_critical_with_wait(tmp_path):
    reg = _critical_registry(tmp_path)
    clock = Clock()
    with pytest.raises(Refused, match="timed out after 20 s"):
        launcher.check_critical(JobSpec("asr", 6, ("x",), gpu=True), reg, 20, clock=clock, sleep=clock.sleep,
                                say=lambda s: None)
    calls = []

    def sleep(s):
        calls.append(s)
        reg.remove("herald-job-train-f-1")                                         # the critical job ends
    launcher.check_critical(JobSpec("asr", 6, ("x",), gpu=True), reg, 600, clock=clock, sleep=sleep,
                            say=lambda s: None)
    assert calls == [5.0]


def test_cli_refuses_gpu_job_next_to_critical(tmp_path):
    raw = yaml.safe_load(mgconfig.DEFAULT_CONFIG.read_text())
    raw["paths"].update(jobs_dir=str(tmp_path / "jobs"), demo_flag=str(tmp_path / "demo_mode"),
                        gpu_lock=str(tmp_path / "gpu.lock"))
    c = tmp_path / "mg.yaml"
    c.write_text(yaml.safe_dump(raw))
    _critical_registry(tmp_path)
    r = subprocess.run([sys.executable, str(ROOT / "scripts/run_job.py"), "--name", "t", "--need-gib", "1", "--gpu",
                        "--config", str(c), "--", "true"], capture_output=True, text=True)
    assert r.returncode == 75 and "critical job is running" in r.stderr


# ---------------------------------------------------------------- the GPU cap and job priority
# A normal job's --need-gib doubles as its torch CUDA cap. A critical job must not be capped by it: on 2026-09-25
# the run F 4B training was started with --need-gib 40, the cap became 40 GiB, and it died with
# "torch.OutOfMemoryError ... 40.00 GiB allowed" while 63.8 GiB of the box was free. For a critical job --need-gib
# is only the condition to start; the cap is applied only when --gpu-max-gib asks for one.


def test_a_normal_job_is_capped_at_its_declared_need():
    from scripts.memguard.launcher import gpu_cap_gib, job_env

    spec = JobSpec(name="bench", need_gib=6, cmd=["true"])
    assert gpu_cap_gib(spec) == 6
    assert job_env(spec, {})["HERALD_GPU_MAX_GIB"] == "6"


def test_a_critical_job_is_not_capped_by_need_gib():
    from scripts.memguard.launcher import gpu_cap_gib, job_env

    spec = JobSpec(name="train-f", need_gib=40, cmd=["true"], gpu=True, priority="critical")
    assert gpu_cap_gib(spec) is None
    assert "HERALD_GPU_MAX_GIB" not in job_env(spec, {})


def test_an_explicit_gpu_max_still_caps_a_critical_job():
    from scripts.memguard.launcher import gpu_cap_gib, job_env

    spec = JobSpec(name="train-f", need_gib=40, cmd=["true"], gpu=True, priority="critical", gpu_max_gib=90)
    assert gpu_cap_gib(spec) == 90
    assert job_env(spec, {})["HERALD_GPU_MAX_GIB"] == "90"


def test_an_inherited_cap_is_cleared_for_an_uncapped_critical_job():
    """A stale HERALD_GPU_MAX_GIB in the parent environment must not silently cap a critical job."""
    from scripts.memguard.launcher import job_env

    spec = JobSpec(name="train-f", need_gib=40, cmd=["true"], gpu=True, priority="critical")
    assert "HERALD_GPU_MAX_GIB" not in job_env(spec, {"HERALD_GPU_MAX_GIB": "12"})


def test_the_gpu_cap_hook_does_nothing_without_a_budget(monkeypatch):
    """The hook must be inert when run_job sets no cap (it reads the env var and returns on a bad/absent value)."""
    import runpy

    monkeypatch.delenv("HERALD_GPU_MAX_GIB", raising=False)
    runpy.run_path(str(ROOT / "scripts/memguard/gpucap/sitecustomize.py"), run_name="not_main")
