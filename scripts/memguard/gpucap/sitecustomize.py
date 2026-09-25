"""Per-job GPU budget for torch (put on PYTHONPATH by scripts/run_job.py; docs/MEMORY_SAFETY.md).

On the GB10, CUDA allocations are not charged to the job's cgroup, so MemoryMax cannot cap them. When the job imports
torch, this hook caps the CUDA caching allocator at HERALD_GPU_MAX_GIB (torch.cuda.set_per_process_memory_fraction)
the moment CUDA initialises, so a job over its budget fails with a CUDA OOM in its own process instead of starving
the machine. Standard library only; it never imports torch itself; any other sitecustomize still runs.
"""
import os
import sys


def _install():
    try:
        budget = float(os.environ.get("HERALD_GPU_MAX_GIB", ""))
    except ValueError:
        return
    if budget <= 0:
        return
    import importlib.abc

    def patch(cuda):
        real = cuda._lazy_init
        busy = []

        def lazy_init():
            real()
            if busy or getattr(cuda, "_herald_capped", False):
                return
            busy.append(1)
            try:
                for d in range(cuda.device_count()):
                    total = cuda.get_device_properties(d).total_memory / 2 ** 30
                    cuda.set_per_process_memory_fraction(min(1.0, budget / total), d)
                cuda._herald_capped = True
                print(f"[herald run_job] torch CUDA allocator capped at {budget:g} GiB "
                      f"(job {os.environ.get('HERALD_JOB', '?')})", file=sys.stderr, flush=True)
            finally:
                busy.clear()
        cuda._lazy_init = lazy_init

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name != "torch.cuda":
                return None
            for f in sys.meta_path:
                if f is self or not hasattr(f, "find_spec"):
                    continue
                spec = f.find_spec(name, path, target)
                if spec is not None and spec.loader is not None and hasattr(spec.loader, "exec_module"):
                    orig = spec.loader.exec_module

                    def exec_module(module, _orig=orig):
                        _orig(module)
                        patch(module)
                    spec.loader.exec_module = exec_module
                    sys.meta_path.remove(self)
                    return spec
            return None

    sys.meta_path.insert(0, Finder())


def _chain():
    """Run the sitecustomize this one shadows, if the environment has one."""
    import importlib.machinery
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    rest = [p for p in sys.path if os.path.abspath(p or ".") != here]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", rest)
    if spec and spec.origin and os.path.abspath(spec.origin) != os.path.abspath(__file__):
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)


try:
    _install()
except Exception as e:  # never break the job's interpreter
    print(f"[herald run_job] GPU cap hook not installed: {e}", file=sys.stderr)
try:
    _chain()
except Exception:
    pass
