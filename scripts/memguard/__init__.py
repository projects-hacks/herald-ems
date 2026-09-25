"""Herald's memory-safety layer for the GB10 (122 GiB unified CPU/GPU memory, no swap): docs/MEMORY_SAFETY.md.

config    loads and validates config/memguard.yaml (the content: thresholds, protected stack, victim order)
probe     reads the machine: /proc/meminfo, PSI, the process table, listening ports, nvidia-smi (I/O only)
policy    pure decisions: memory level, protection, victim classes and order (no I/O, unit-tested)
actions   terminates a victim (SIGTERM, grace, SIGKILL) or stops a vLLM service through ZRT
state     the status file, the JSON-lines log, the demo-mode flag and the guarded-job registry
daemon    the watchdog loop (scripts/memguard.py run)
launcher  the one launcher for model-loading jobs (scripts/run_job.py)
gpucap/   a sitecustomize hook that caps a job's torch CUDA allocator at its --need-gib budget
"""
