# Memory safety on the ZGX Nano (GB10)

Owner: infra (backend). Read this before you start anything that loads a model or a large dataset on the team Nano:
training, merges, benchmarks, Whisper or TTS jobs, or a new vLLM service. The short rule is in `AGENTS.md`
(pitfalls): **every model-loading job goes through `scripts/run_job.py`**, and during the demo **demo mode is on**.

## 1. What happened (2026-09-24, 19:35 UTC)

The box ran out of memory and **froze until a manual reboot**. Every service died, including the demo stack.

- Three vLLM models were being served and held about 71 GB. About 14 GB was free.
- Several jobs then loaded models at the same time: two Whisper loads, a Piper TTS process pool and a benchmark.
- The GB10 has **122 GiB of unified memory shared by the CPU and the GPU, and no swap**. There was nowhere to
  put anything. The kernel reclaimed page cache until it was thrashing: it re-read code and weight pages from disk
  over and over. The machine stopped responding before the kernel's OOM killer freed anything useful.
- When the OOM killer did run, it killed **small session daemons** (their `oom_score_adj` was 100 to 200, which
  weighs more than the RSS of a big process with an adjustment of 0), not the processes that held the memory. The
  box stayed hung.

Nothing on the box was watching memory. Nothing stopped two GPU-heavy jobs from starting together. No job had a
memory limit.

## 2. Measured facts about this box (2026-09-24)

| Fact | How it was measured | What it means |
|---|---|---|
| `sudo` needs a password, which agents don't have | `sudo -n true` fails | Everything below runs as `hp18`, with no root. The root-only hardening is in §8 for Rajeev. |
| `systemd-oomd` is inactive; there is no swap; `vm.min_free_kbytes` is 45 MB | `systemctl status systemd-oomd`, `free`, `sysctl vm.min_free_kbytes` | There is no system backstop, and the kernel keeps very little free memory in reserve. |
| The cgroup v2 memory controller **is delegated** to the user manager | `systemd-run --user --scope -p MemoryMax=2G` killed a 4 GiB numpy allocation cleanly (only that process) | Without root, `hp18` can cap the **host** memory of any job it starts. |
| **CUDA allocations on the GB10 are NOT charged to the cgroup** | A 4 GiB `torch` CUDA allocation inside a `MemoryMax=2G` scope succeeded | A cgroup cap alone cannot stop a job from filling the GPU side. `run_job.py` adds a torch allocator cap (§4.3). |
| CUDA allocations **do** lower `MemAvailable` | Live test (ii), §7: a 5.2 GiB CUDA allocation dropped MemAvailable from 82.2 to 76.65 GiB | The guard can watch one number, `MemAvailable`, for both sides of unified memory. |
| PSI is available | `/proc/pressure/memory` | The guard can detect thrashing (`full avg10`) even when MemAvailable looks acceptable. |
| vLLM/ZRT services run as `hp18` | process `VLLM::EngineCore`, parent `/opt/hp/zrt/venv/bin/vllm serve … --served-model-name <label>`, in a `snap.zrt.zrt-*.scope` cgroup; proxy `/snap/zrt/9/bin/zrt __proxy start --mode system` | The guard can see every model server and its label from the command line. It stops them through ZRT, never with `kill -9`. |
| Per-process GPU memory | `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` (about 0.1 s per call) | This is how the guard sizes victims (RSS + GPU). |
| `loginctl enable-linger hp18` works **without sudo** | `Linger=yes` after running it (2026-09-24) | The guard's user service keeps running with nobody logged in, and it starts at boot. |
| `RLIMIT_MEMLOCK` is unlimited for `hp18` | `ulimit -l` | The guard `mlockall`s itself (about 40 MB, `VmLck` in `/proc/<pid>/status`), so its own pages are never evicted while memory is short. |

## 3. The layers

```
 job asks for memory ──► scripts/run_job.py ──► systemd-run --user --scope  (MemoryMax, MemorySwapMax=0,
                         (refuses in demo mode,    oom_score_adj 1000, torch CUDA cap = --need-gib)
                          waits for memory,
                          one GPU job at a time)

 every 0.5 s ──► herald-memguard.service (scripts/memguard.py, systemd --user, Restart=always)
                 MemAvailable + PSI; process table; GPU memory (nvidia-smi, every 2 s)
                 warn  → log + status file
                 kill  → one victim per cycle: (a) normal guarded jobs → (b) other hp18 processes
                         → (c) vLLM services not in the keep-list → (d) critical jobs (last resort,
                         loud warning, 20 s SIGTERM grace); never the protected demo stack
                 demo  → stricter thresholds; any NEW non-protected GPU holder is terminated at once

 kernel OOM killer (last resort): prefers guarded jobs (oom_score_adj 1000)
 optional root hardening (§8): vm.min_free_kbytes 1 GiB, zram swap, earlyoom
```

| Layer | Stops | Doesn't stop |
|---|---|---|
| `run_job.py` wait + GPU lock | Two big loads at once (the cause of the freeze). A job starting when there isn't room. | Jobs not started through it. |
| cgroup `MemoryMax` | A job's host memory growing past its cap (the kernel kills it inside its own scope). | CUDA allocations (not charged, §2). |
| torch allocator cap (`gpucap/sitecustomize.py`) | A torch job allocating CUDA memory past its budget: a clean `torch.OutOfMemoryError` in its own process. | Non-torch CUDA users (vLLM, TensorRT, raw CUDA). cuBLAS/cuDNN workspaces outside the caching allocator. |
| The guard | Anything of `hp18`'s that takes the box below the kill threshold, whoever started it. Thrashing (PSI). Strangers on the GPU during the demo. | Other users' or root's processes (it can't signal them). |
| `oom_score_adj 1000` | If the kernel OOM killer does run, it takes a guarded job, not a session daemon. | Thrashing before the OOM killer runs (that's what the guard is for). |

## 4. How to run jobs

### 4.1 The rule

Any job that loads a model or a lot of data runs through `scripts/run_job.py`:

```bash
PY=~/miniforge3/envs/zgx/bin/python
scripts/run_job.py --name <name> --need-gib <N> [--gpu] [--priority normal|critical] [--host-max-gib M] \
                   [--gpu-max-gib G] [--wait S] -- <command …>

# the 30B training (about 77 GiB): GPU-heavy and critical (killed last, §4.4)
scripts/run_job.py --name train-f --priority critical --gpu --need-gib 80 -- $PY scripts/train_vlm_lora.py …
# a Whisper batch job: 6 GiB, GPU
scripts/run_job.py --name asr --need-gib 6 --gpu -- $PY scripts/asr_layer.py transcribe …
# a CPU data job: 20 GiB of host memory, no GPU
scripts/run_job.py --name build-set --need-gib 20 -- $PY scripts/build_train_set.py …
# see exactly what it would run
scripts/run_job.py --name x --need-gib 4 --dry-run -- true
```

What it does, in order:

1. **Refuses in demo mode** (exit code 75), and keeps checking while it waits.
   With `--gpu`, it also **refuses while a critical job is running** (exit 75, naming the critical job), instead of
   queueing silently for hours behind a training run. With `--wait S`, it waits up to S seconds for the critical job
   to end instead.
2. With `--gpu`, **takes an exclusive `flock` on `~/.cache/herald-gpu.lock`**. One GPU-heavy job runs at a time;
   others queue ("GPU busy (<holder>); queued"). The lock file names the holder. The lock is passed to the job
   itself, so it is held for as long as the job runs, even if the launcher dies.
3. **Waits until `MemAvailable − reserve ≥ --need-gib`** (`run_job.reserve_gib` = 12 GiB: the 8 GiB kill threshold
   plus 4 GiB of margin). It prints a line every 30 s while waiting and gives up after `wait_timeout_s` (30 min;
   `--wait` overrides) with exit code 75.
4. **Runs the command in a transient systemd user scope**:
   `systemd-run --user --scope --unit herald-job-<name>-<UTC time> -p MemoryMax=<M> -p MemorySwapMax=0 -- <cmd>`.
   `M` is `--host-max-gib`, or `--need-gib + 4 GiB` by default. The command runs with `oom_score_adj 1000`
   (inherited by its children), so the kernel's OOM killer takes it before anything else.
5. **Exports** `HERALD_JOB=<name>`, `HERALD_GPU_MAX_GIB=<--gpu-max-gib or --need-gib>`, and puts
   `scripts/memguard/gpucap/` first on `PYTHONPATH`. Its `sitecustomize.py` watches for `torch.cuda` being imported
   and, the moment CUDA initialises, calls `torch.cuda.set_per_process_memory_fraction(budget / total)` on every
   device. It prints `[herald run_job] torch CUDA allocator capped at N GiB` to stderr. It never imports torch
   itself, and it chains to any other `sitecustomize` on the path.
6. **Registers the job** in `~/.local/state/herald/jobs/<unit>.json` (name, **priority**, pid, need, caps,
   command). The priority is also exported as `HERALD_JOB_PRIORITY`. The guard reads it back from the job's
   environment if the registry file is missing. The file is
   removed when the job exits; the guard prunes entries whose launcher has died.
7. Forwards SIGINT/SIGTERM/SIGHUP to the job and **exits with the job's exit code** (128 + signal if it was killed).

### 4.1a `--need-gib` is a cap for normal jobs, a start condition for critical ones

For a **normal** job `--need-gib` does double duty: it is the amount waited for *and* the torch CUDA cap, so a job
that goes over its declared budget fails with a CUDA OOM in its own process (§4.3) instead of starving the box.

For a **`--priority critical`** job it is only the condition to start. The run is the thing the team cannot lose, and
capping it at the figure someone guessed when they typed the command is worse than letting it use the memory that is
actually free. A critical job is capped only when `--gpu-max-gib` is given explicitly.

Why this changed (2026-09-25): the run F 4B training was started with `--need-gib 40`. That became a 40 GiB torch
cap, and training died at step 39 with `torch.OutOfMemoryError: CUDA out of memory … 40.00 GiB allowed` while
**63.8 GiB of the box was free** — the job starved itself, and nothing else on the machine was under pressure. The
guard was never involved. Tests: `tests/test_run_job.py` (a normal job is capped at its need, a critical job is not,
an explicit `--gpu-max-gib` still caps it, an inherited `HERALD_GPU_MAX_GIB` is cleared, and the hook is inert with
no budget set).

### 4.2 Choosing `--need-gib`

`--need-gib` is the total the job will hold, host plus GPU, because on this box they are the same memory. It is also
the torch CUDA cap, so leave margin: if the job goes over it, it fails with its own CUDA OOM, which is what we want,
but it has to be rerun. For training, use the peak you measured plus about 5%. Use `--gpu-max-gib` when the CUDA
budget should differ from the total (for example, a job that loads 40 GiB into host memory and then moves 20 GiB to
the GPU).

### 4.3 Why the torch cap exists

On the GB10, CUDA allocations are not charged to the cgroup (§2), so `MemoryMax` cannot stop a torch job from taking
the GPU side of unified memory. The cap makes the torch job fail inside its own process instead. Measured in live
test (iii), §7: with `--need-gib 2`, the third 1 GiB allocation raised
`torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 1024.00 MiB …` and the job exited with code 1.
Nothing else on the box noticed.

### 4.4 Priority: `--priority critical` (the training run)

The team can't lose the training run, so it is started with `--priority critical`. The trainer's supervisor loop
calls `scripts/run_job.py --name train-f --priority critical --gpu --need-gib N -- …`. A critical job:

- is victim class **(d)**, killed **only after** every normal guarded job, every other `hp18` process and every
  non-keep-list vLLM service. It is the last resort before the box freezes.
- If the guard does reach it, the guard first logs a loud `critical_kill` event ("LAST RESORT: terminating CRITICAL
  job …"). It then sends SIGTERM and waits `critical_term_grace_s` (**20 s**) before SIGKILL, so the trainer can
  finish or abandon a checkpoint save cleanly (transformers writes checkpoints atomically).
- **blocks other GPU jobs:** `run_job.py --gpu` refuses (exit 75) while it runs, unless `--wait` is given.
- **makes the guard name who threatens it:** while a critical job runs, the guard's `warn` event is logged every
  `critical_warn_log_every_s` (10 s) at the warn *and* kill levels. It carries `critical_jobs` and `growing`: the
  top 5 processes by growth in RSS + GPU memory over `growth_window_s` (10 s), protected or not, with their owner
  (a protected reason, a victim class, or another uid). For example:
  `"growing": [{"pid": 96851, "grew_gib": 5.82, "owner": "…", "cmd": "…uvicorn herald.app:app --port 8197"}]`.
  Read them with `scripts/memguard.sh logs | grep growing`.

The protected demo stack still ranks above a critical job: during the demo, the guard never touches it. In demo mode
`run_job` refuses everything anyway, so don't train during the demo.

### 4.5 Jobs that don't use `run_job.py`

The guard still sees them. They are class (b): they are killed after guarded jobs, largest first, when memory is
short. The data agents' Whisper jobs that run under `flock ~/.cache/herald-whisper.lock` are in this class until
they move to `run_job.py`.

## 5. The memory guard

`scripts/memguard.py` (entry) and the package `scripts/memguard/`:

| Module | Responsibility |
|---|---|
| `config.py` | Loads and validates `config/memguard.yaml` into frozen dataclasses. Bad values raise `ConfigError` (kill ≥ warn, a bad regex, an unknown victim class, a PSI value over 100, a port out of range, a negative OOM adjustment). |
| `probe.py` | Reads the machine: `/proc/meminfo`, `/proc/pressure/memory`, `/proc/<pid>/{stat,status,cmdline,exe,cgroup}`, listening sockets (`/proc/net/tcp{,6}` + `/proc/<pid>/fd`), and `nvidia-smi` (cached for `gpu_poll_s`). |
| `policy.py` | Pure decisions, no I/O: the level (`ok`/`warn`/`kill`), who is protected, the victim groups and their order, the demo-mode GPU rule. |
| `actions.py` | Terminates a victim. SIGTERM, `term_grace_s` (3 s), then SIGKILL (and `cgroup.kill` for a job scope). A vLLM service is stopped with `sg zrt -c "zrt service stop <label>"`, and only if ZRT doesn't stop it within 30 s does the guard send SIGTERM to the `vllm serve` process (a graceful shutdown). It never sends `kill -9` to a model server. PIDs are held as pidfds and checked against their start time, so a recycled PID is never signalled. |
| `state.py` | The status file, the JSON-lines log, the demo flag, the job registry. |
| `daemon.py` | The loop. |
| `launcher.py` | `run_job.py`'s logic. |
| `gpucap/sitecustomize.py` | The torch CUDA cap. |

### 5.1 Every tick (2 Hz)

1. It reads `MemAvailable`, `MemTotal` and PSI `full avg10`.
2. It picks the thresholds for the mode (normal or demo) and computes the level:
   - `kill` if MemAvailable < `kill_below_gib` **or** PSI full avg10 > `psi_full_avg10_kill`;
   - `warn` if MemAvailable < `warn_below_gib`;
   - otherwise `ok`.
3. It reads per-process GPU memory. `nvidia-smi` runs at most every 2 s, and the last reading is reused in between.
4. It re-reads the process table and classifies it. This happens every tick while the level isn't `ok` or demo mode is
   on, and once a second otherwise. It costs about 0.1 s of CPU per second, and the guard uses about 40 MB.
5. If a kill is in progress, it advances it: whether the victim is gone, and the SIGKILL once the grace period has
   passed. After a victim is gone, it waits `settle_s` (2 s) for the memory to come back before choosing again.
6. Otherwise it acts on the first rule that applies:
   - **Demo mode:** a non-protected group that holds ≥ 64 MiB of GPU memory in a process **started after demo mode
     was switched on** is terminated at once, whatever the thresholds say.
   - **Level `kill`:** the first victim in kill order is terminated. **Only one kill happens per cycle**, and the
     guard re-evaluates afterwards. If there is no eligible victim, it logs `no_victim` (every 30 s at most).
7. At level `warn`, it logs the reason and the next three victims, every 30 s at most (and on every level change).
8. It writes the status file.

### 5.2 Who is protected (never a victim)

From `config/memguard.yaml` → `protected`:

- **Processes listening on the demo ports**, and their descendants: 8100 (the demo Herald app), 8080 (the ZRT proxy),
  8200 (the ED receiver), 9000 and 8474 (Toxiproxy's link and its API).
- **vLLM services whose `--served-model-name` is in `vllm_keep`** (`ems-e-v2-fp8`, `herald-f`, `qwen3vl-fp8`), with
  their whole process tree (the `vllm serve` parent and its `VLLM::EngineCore`).
- **Command-line rules** (regexes on the full command line): the ZRT proxy and CLI, the ED receiver, the Herald app on
  port 8100, Toxiproxy, sshd, systemd and D-Bus, desktop and session daemons, IDE servers (VS Code, Kiro, Cursor),
  agent CLIs, the guard itself (and its ancestors), the job launcher, interactive shells, and sudo/login.
  Shells are protected but their children aren't, so a job started from a shell can be a victim, while the shell
  (an agent's session, for example) survives.
- **Other users' processes** are never touched (`hp18` can't signal them anyway).

A process inside a `herald-job-*` scope is **never** protected by a command-line rule. A guarded job that runs
`bash -c …` is still a whole victim.

### 5.3 Victim classes, in order

Inside a class, the largest group (RSS + GPU memory) goes first. Groups smaller than `min_victim_gib` (0.5 GiB) are
skipped, because killing them wouldn't help.

| Class | What | A group is | How it's stopped |
|---|---|---|---|
| (a) `guarded_jobs` | Every process in a `herald-job-*` systemd scope (started by `run_job.py`) | the whole scope | SIGTERM to everything in the scope's `cgroup.procs`, 3 s, then `cgroup.kill` + SIGKILL |
| (b) `user_processes` | Every other `hp18` process that isn't protected | a same-executable process tree (a worker pool dies with its parent; a Python job's `ffmpeg` child is its own group) | SIGTERM, 3 s, SIGKILL |
| (c) `vllm_services` | vLLM services whose label is **not** in `vllm_keep` | the `vllm serve` tree | `sg zrt -c "zrt service stop <label>"`; SIGTERM to `vllm serve` only if ZRT hasn't stopped it after 30 s |
| (d) `critical_jobs` | Guarded jobs started with `--priority critical` (the training run) | the whole scope | a `critical_kill` warning event, then SIGTERM, **20 s** (`critical_term_grace_s`), then `cgroup.kill` + SIGKILL |

### 5.4 Thresholds (`config/memguard.yaml`)

| Setting | Normal | Demo | Why |
|---|---|---|---|
| `warn_below_gib` | 16 | 20 | About the size of one more model load. A warning gives people time to react. |
| `kill_below_gib` | 8 | 12 | Far above the point where the freeze began (the box thrashed with about 14 GB "free" of 122, while several loads were still growing). The kernel keeps only 45 MB free by default, and reclaim starts thrashing well before 0. |
| `psi_full_avg10_kill` | 25 % | 15 % | "full" means every non-idle task was stalled on memory. 25 % over 10 s is thrashing even if MemAvailable still looks acceptable, because hot file pages are being evicted and re-read. |
| `poll_hz` | 2 | 2 | At 1 GiB/s of growth, the guard sees each 0.5 GiB step. |
| `gpu_poll_s` | 2 | 2 | `nvidia-smi` costs about 0.1 s. |
| `term_grace_s`, `settle_s` | 3, 2 | same | A clean exit for well-behaved jobs; memory returns before the next decision. |

### 5.5 Files

| Path | Written by | Contents |
|---|---|---|
| `~/.local/state/herald/memguard.json` | guard, each tick (atomic replace) | `ts` (heartbeat), `heartbeat` (ISO), `pid`, `mode`, `level`, `reason`, `available_gib`, `total_gib`, `psi_full_avg10`, `psi_some_avg10`, `thresholds`, `dry_run`, `protected_pids`, `jobs`, `killing` (the victim in progress), `last_action` |
| `~/.local/state/herald/memguard.jsonl` | guard | One JSON event per line: `start`, `stop`, `mode`, `level`, `warn` (with the next victims, plus `critical_jobs` and `growing` while a critical job runs), `critical_kill`, `kill`, `sigkill`, `escalate`, `victim_gone`, `no_victim`, `would_kill` (dry run), `error`, `note`. Each event also goes to the journal. |
| `~/.local/state/herald/demo_mode` | `scripts/demo_mode.sh` | Present means demo mode is on. Its mtime is the switch-on time used by the GPU rule. |
| `~/.local/state/herald/jobs/*.json` | `run_job.py` | One file per running guarded job. |
| `~/.cache/herald-gpu.lock` | `run_job.py --gpu` | The flock, plus the holder's name. |

`last_action` is the newest `kill`/`critical_kill`/`sigkill`/`escalate`/`victim_gone`/`no_victim`/`would_kill` event. It survives a
guard restart (it is read back from the end of the log).

### 5.6 Commands

```bash
scripts/memguard.sh install      # write ~/.config/systemd/user/herald-memguard.service, enable --now, enable linger
scripts/memguard.sh status       # systemd state + the status file (exit 1 if the heartbeat is older than 5 s)
scripts/memguard.sh logs [N]     # last N events
scripts/memguard.sh restart      # after changing config/memguard.yaml or the guard's code
scripts/memguard.sh uninstall
$PY scripts/memguard.py once     # one classification, printed: the protected processes and the victims in kill order
$PY scripts/memguard.py run --dry-run --config <file>   # log `would_kill` instead of killing (for trying a config)
```

The unit runs `~/miniforge3/envs/zgx/bin/python <repo>/scripts/memguard.py run` from Rajeev's copy (the demo
instance), with `Restart=always`, `RestartSec=2`, no start-rate limit, and `LimitMEMLOCK=infinity`. It is enabled in
`default.target`, and linger is on, so it starts at boot with nobody logged in. **After editing the guard or its
config, run `scripts/memguard.sh restart`**: the running guard keeps the code and config it started with.

## 6. Demo mode

```bash
scripts/demo_mode.sh on        # before the demo: flag on; it prints the current GPU holders you may want to stop
scripts/demo_mode.sh status
scripts/demo_mode.sh off       # after the demo
```

While demo mode is on:

- `run_job.py` **refuses every job** (exit 75), including ones already waiting for memory or the GPU lock.
- The guard uses the **demo thresholds** (warn 20 GiB, kill 12 GiB, PSI 15 %).
- Any **new non-protected process holding GPU memory is terminated at once**, whatever the thresholds say. "New"
  means it started after demo mode went on. GPU holders that already exist are listed by `demo_mode.sh on` so you
  can stop them deliberately. The protected demo stack (§5.2) is never touched.

### 6.1 Starting the demo instance

```bash
scripts/memguard.sh status     # running, heartbeat fresh
scripts/demo_mode.sh on
HERALD_ED_URL=http://127.0.0.1:9000 scripts/run_demo.sh     # port 8100
```

`scripts/run_demo.sh` differs from `run_dev.sh` in three ways:

- **It doesn't use `--reload`.** `run_dev.sh` restarts the server on any file edit under `herald/` or `web/`, which
  would drop the incident mid-demo.
- **`HERALD_STT_PRELOAD=1`:** Whisper is loaded and warmed before the server accepts requests. Its memory is claimed
  up front, and a failed load stops startup (the lifespan raises, and uvicorn exits with "Application startup
  failed") instead of failing on the first utterance on stage.
- **It refuses to start** unless `herald-memguard.service` is active, the guard's heartbeat is under 5 s old, and demo
  mode is on. `HERALD_DEMO_SKIP_CHECKS=1` overrides this with a loud warning.

`GET /api/health` now carries `memory: {available_gib, total_gib, guard: {running, mode, last_action}}`. The UI
contract is in `docs/UX_PLAN.md` §5. `running` means the guard's heartbeat is under `HERALD_MEMGUARD_STALE_S` (5 s)
old.

### 6.2 The demo memory budget (final stack)

| Component | Memory | Source |
|---|---|---|
| `herald-f` (Qwen3-VL-30B-A3B + merged LoRA, FP8) at `--gpu-memory-fraction 0.35` | ≈ 42.6 GiB (0.35 × 121.6) GPU + ≈ 4 GiB host (the `vllm serve` process and EngineCore RSS) | serve flags in `scripts/serve_models.sh`; host RSS measured on `ems-e-v2-fp8` (1.3 + 2.6 GiB) |
| Herald app (FastAPI + Whisper large-v3-turbo + the protocol embedder + RxNorm index) | ≈ 4–6 GiB RSS + ≈ 2.2 GiB GPU | measured on the :8100 instance, 2026-09-24 (4.0–6.0 GiB RSS, 2258 MiB GPU) |
| ED receiver + Toxiproxy | < 0.2 GiB | measured |
| OS, desktop, sshd, IDE servers, agent CLIs | ≈ 6–8 GiB | measured (`memguard.py once`) |
| **Total** | **≈ 60–63 GiB** | |
| **Headroom** | **≈ 58 GiB of 121.6**, far above the demo kill threshold (12 GiB) | |

If `ems-e-v2-fp8` (0.12 → about 12.5 GiB GPU + about 4 GiB host) or `qwen3vl-fp8` (0.35 → about 43 GiB) is served
next to `herald-f`, add those figures. Three 0.35 services (about 128 GiB) cannot fit; that is what froze the box.

## 7. Live test (2026-09-24, 22:47 UTC)

The test ran against a **test config**: `kill_below_gib` = MemAvailable at the start (83.0 GiB) − 6 = 77 GiB,
`warn_below_gib` 79, with victims limited to guarded jobs, and every process without the test marker in its command
line protected. Its state files were in a scratch directory. The Whisper jobs of other agents, the demo stack and the
installed real guard kept running. MemAvailable never went below 76.6 GiB.

| Step | Result |
|---|---|
| (i) Host allocator via `run_job.py --need-gib 4 --host-max-gib 16`, +1 GiB/s | The level went `warn` at 78.9 GiB and `kill` at 76.9 GiB (22:47:09.839). `kill` (SIGTERM to the scope) came **38 ms later**, at 6.0 GiB RSS; `victim_gone` came 0.5 s later. `run_job` exited 143 (SIGTERM). |
| (ii) torch CUDA allocator via `run_job.py --gpu --need-gib 14`, +1 GiB/s up to 12 | The cap hook printed "capped at 14 GiB". MemAvailable fell 82.2 → 76.65 GiB as CUDA memory grew, which **confirms that the GB10's CUDA allocations show in MemAvailable**. `kill` came 79 ms after the level change, at 0.6 GiB RSS + 5.19 GiB GPU, and the job was gone 0.5 s later. |
| (iii) Per-job GPU cap: `--need-gib 2`, allocating 4 × 1 GiB | 1 and 2 GiB succeeded; the third raised `torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 1024.00 MiB`. The job exited 1, and **the guard didn't need to act**. |
| (iv) Demo mode (test flag on) | `run_job.py` → `refused: demo mode is on`, exit 75. A new plain Python process allocating 1 GiB of CUDA memory (not through `run_job`) was terminated with reason `demo mode: new non-protected GPU process` about 1 s after it began holding GPU memory (2.6 s after launch, including the torch import). |
| Survivors after every step | `ems-e-v2-fp8` (EngineCore pid 4910, up 2 h 50 min) answered `/v1/models` and a chat completion. The Herald app on :8100 answered `/api/health` (200, `stt_loaded: true`). The ED receiver :8200 returned 200. Toxiproxy's `/proxies` answered. The data agent's `asr_layer.py transcribe` (pid 64103) kept running. |

### 7.1 Critical priority (2026-09-24, 23:02 UTC)

This test also used a test config: kill at 81.8 GiB (MemAvailable 89.8 − 8), warn at 85.8, victims limited to
guarded and critical jobs, and everything without the test marker protected.

| Step | Result |
|---|---|
| A dummy critical job (`--priority critical --gpu --need-gib 4`, holding 3 GiB) | Started; the registry recorded `priority: critical`. |
| A `--gpu` job while it ran | `refused: a critical job is running: live-critical (herald-job-live-critical-…). GPU jobs are refused while it runs; pass --wait <seconds> to queue behind it`. Exit 75. |
| A dummy normal job growing 1 GiB/s | The `warn` events every 2 s (the test setting) named the critical job and listed `growing`: the critical dummy (+3.01 GiB), the normal dummy (+1.01, then +3.01 GiB), and a Herald test instance someone else started on :8197 (+1.45, then +5.82 GiB). At the kill level (79.8 GiB) the guard **killed the normal job first** (`guarded_jobs`); the critical job kept running. |
| After that | The :8197 instance kept growing, and in this test config it was protected, so memory stayed below the kill threshold. With nothing else allowed, the guard reached the last resort 2 s later (after `settle_s`). It logged `critical_kill` ("LAST RESORT …") and sent SIGTERM to the critical job. The dummy has no SIGTERM handler, so it exited at once, without the 20 s wait. With the real config, that :8197 instance is class (b) and would have been killed before the critical job. The 20 s grace before SIGKILL is covered by `test_terminator_critical_grace_and_warning`. |

The unit tests are `tests/test_memguard.py`, `tests/test_run_job.py` and `tests/test_memory_health.py`. They cover
config loading and every validation error, the level boundaries, protection (never a victim), class order and
largest-first, tiny-group filtering, the keep-list, the demo GPU rule, the parsers, the terminator on real child
processes (SIGTERM, escalation to SIGKILL, refusing a recycled PID), a dry-run guard tick, the launcher's demo
refusal and exit code, the memory wait and its timeout, the GPU lock, the `systemd-run` command and caps, the job
environment, the registry, the GPU hook staying inert without torch, and `/api/health`'s `memory` block and the
STT preload.

## 8. Optional hardening that needs root (Rajeev)

None of this is required for the guard to work. Each item makes the last-resort behaviour better if the guard is
ever stopped or outrun. Run the commands yourself; agents don't have the password.

### 8.1 A bigger kernel free-memory reserve

With 45 MB, the kernel starts direct reclaim very late on a 122 GiB box. With 1 GiB it wakes `kswapd` earlier and
keeps room for its own allocations (network buffers, page tables) when memory is tight.

```bash
printf 'vm.min_free_kbytes = 1048576\nvm.watermark_scale_factor = 100\n' | sudo tee /etc/sysctl.d/60-herald-memory.conf
sudo sysctl --system
sysctl vm.min_free_kbytes vm.watermark_scale_factor     # check
```

This costs 1 GiB that nobody can allocate.

### 8.2 A small zram swap

Compressed swap in RAM gives the kernel somewhere to put cold anonymous pages (idle daemons, the desktop) instead of
evicting hot file pages and thrashing. Guarded jobs keep `MemorySwapMax=0`, so they never swap.

```bash
sudo apt-get install -y zram-tools
printf 'ALGO=zstd\nPERCENT=8\nPRIORITY=100\n' | sudo tee /etc/default/zramswap     # about 10 GiB of zram
sudo systemctl restart zramswap
swapon --show                                                                     # check
```

### 8.3 earlyoom as a system backstop

It acts below the guard's kill threshold, so it only fires if the guard isn't running or was outrun. It runs as root,
so it can also kill other users' processes.

```bash
sudo apt-get install -y earlyoom
sudo tee /etc/default/earlyoom >/dev/null <<'EOF'
EARLYOOM_ARGS="-m 4,2 -s 100,100 -r 60 --prefer '^(python3?|python3\.[0-9]+|piper)$' --avoid '^(sshd|systemd|systemd-.*|zrt|toxiproxy-serv|VLLM::EngineCor|vllm|Xorg|gnome-shell)$' -n"
EOF
sudo systemctl enable --now earlyoom
journalctl -u earlyoom -n 5      # check: "mem avail: … sending SIGTERM when <= 4.00%"
```

`-m 4,2` sends SIGTERM at 4 % available (about 4.9 GiB) and SIGKILL at 2 %. The guard's kill threshold is 8 GiB, so
the guard acts first.

### 8.4 Guard priority (optional)

As a user service, the guard runs with `oom_score_adj` 200, which is the user manager's default. Lowering it needs
root. The guard is small and `mlockall`ed, and `Restart=always` brings it back in 2 s. To also protect it from the
kernel OOM killer:

```bash
sudo mkdir -p /etc/systemd/system/user@1000.service.d
printf '[Service]\nOOMScoreAdjust=-100\n' | sudo tee /etc/systemd/system/user@1000.service.d/oom.conf
sudo systemctl daemon-reload     # takes effect at the next login/boot of the user manager
```

## 9. Limits and caveats

- The guard only sees and signals `hp18`'s processes. Root services (Docker, for example) are outside it; earlyoom
  (§8.3) covers them.
- The torch cap covers the torch caching allocator only. vLLM is capped by its own `--gpu-memory-fraction`, and other
  CUDA users by their own settings.
- A class (b) victim is a same-executable process tree. A job made of different executables (a shell pipeline, for
  example) loses its biggest member first, and the rest on later cycles if memory is still short. Use `run_job.py`,
  whose scope is always killed as a whole.
- Keep `vllm_keep` in step with what the demo serves. A label that isn't on the list is class (c) and gets stopped
  when memory is short.
- A critical job is protected by order, not immunity. If the protected demo stack, or another user, keeps growing after
  every other victim is gone, the critical job is still terminated (with the 20 s grace) rather than letting the box
  freeze. The `growing` list in the `warn` events shows who did it.
- The guard reacts at 2 Hz. A job allocating much faster than about 4 GiB/s from 12 GiB above the kill threshold could
  still get ahead of it, which is why `run_job.py` makes big jobs wait for room before they start.
