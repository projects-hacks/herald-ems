#!/usr/bin/env python3
"""Run the whole run F gate table (docs/TRAINING_PLAN.md §6) and write one pass/fail report.

The gates themselves live in `config/gates.yaml`; this file only runs them. It exists so that the comparison between
E v2, the 4B run F, the 30B's two epoch adapters and the untuned vision model is one command with one report, instead
of thirty invocations whose numbers get copied by hand.

    scripts/run_gates.py --dry-run                      # print the plan, run nothing
    scripts/run_gates.py --levels f-e2                  # every gate for one level
    scripts/run_gates.py --levels f-e2 --gates rerank   # one gate
    scripts/run_gates.py --report-only                  # rebuild the report from results.jsonl

What it deliberately does NOT do:
  * start model servers. `zrt serve` runs in the foreground and dies with the shell that started it (AGENTS.md
    pitfalls: a healthy qwen3vl-fp8 was killed that way), so the runner checks whether the label answers and stops
    with the exact detached command if it does not.
  * run two jobs at once. Every bench goes through `scripts/run_job.py`, one at a time.

It is resumable: each (level, gate, run) is appended to `runs/gates/results.jsonl` as it finishes, and a rerun skips
what is already there. A freeze mid-table costs one bench, not the table.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OPS = {
    ">=": lambda got, want: got >= want,
    "<=": lambda got, want: got <= want,
    "==": lambda got, want: got == want,
}


def load_gates(path: Path | None = None) -> dict:
    """The gate table, with ${HF_REPO_ID} expanded from the environment."""
    import os

    from herald.config import load_yaml

    cfg = load_yaml("gates.yaml") if path is None else __import__("yaml").safe_load(path.read_text())
    for lvl in cfg["levels"].values():
        if "repo" in lvl:
            lvl["repo"] = os.path.expandvars(lvl["repo"])
    return cfg


def dig(obj: dict, dotted: str):
    """`groups.broad.f1` -> obj["groups"]["broad"]["f1"]; None if any hop is missing."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def json_lines(text: str) -> list[dict]:
    """Every standalone JSON object printed on its own line. Benches also print progress, which is skipped."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def pick(lines: list[dict], select: dict | None) -> dict | None:
    """The result line a gate scores: the last one matching `select`, or simply the last one."""
    if select:
        lines = [ln for ln in lines if all(str(ln.get(k)) == str(v) for k, v in select.items())]
    return lines[-1] if lines else None


def served(endpoint: str, label: str, timeout: float = 5.0) -> bool:
    """Is this label answering on the local model server? ZRT routes by service label only (AGENTS.md)."""
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/models", timeout=timeout) as r:
            body = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False
    return any(m.get("id") == label for m in body.get("data", []))


def serve_hint(level_id: str, lvl: dict) -> str:
    if lvl.get("serve"):
        return f"scripts/serve_models.sh {lvl['serve']}    # detached, see AGENTS.md"
    repo = lvl.get("repo", "<merged repo>")
    note = lvl.get("serve_note", "")
    return (f"setsid nohup env MAX_JOBS=3 NVCC_THREADS=1 sg zrt -c \"zrt serve hf:{repo} --label {lvl['label']} ...\" "
            f"> runs/serve/{level_id}.log 2>&1 < /dev/null &" + (f"\n      # {note}" if note else ""))


def applicable(gate: dict, level: dict) -> tuple[bool, str]:
    if gate.get("manual"):
        return False, "judged by a human"
    if gate["group"] not in level.get("groups", []):
        return False, f"level has no {gate['group']} role"
    req = gate.get("requires_file")
    if req and not (ROOT / req).exists():
        return False, f"needs {req}"
    return True, ""


def run_one(cfg: dict, gate: dict, level: dict, run: int, dump: Path, dry: bool) -> dict:
    """One bench invocation through run_job.py. Returns the record to append to results.jsonl."""
    cmd = [str(ROOT / "scripts" / "run_job.py"), "--name", f"gate-{gate['id']}", "--need-gib", str(cfg["need_gib"]),
           "--wait", "1800", "--", sys.executable]
    cmd += [c.format(label=level["label"], dump=str(dump)) for c in gate["cmd"]]
    if dry:
        print("    " + " ".join(cmd[cmd.index("--") + 1:]))
        return {}
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    line = pick(json_lines(p.stdout), gate.get("select"))
    rec = {"gate": gate["id"], "group": gate["group"], "run": run, "exit": p.returncode,
           "seconds": round(time.time() - t0, 1),
           "metrics": {name: dig(line, path) for name, path in (gate.get("metrics") or {}).items()} if line else {},
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    if line is None:
        rec["error"] = (p.stderr or p.stdout or "no JSON result line").strip()[-400:]
    return rec


def medians(records: list[dict], metric: str) -> tuple[float | None, list]:
    vals = [r["metrics"].get(metric) for r in records if r.get("metrics", {}).get(metric) is not None]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return (statistics.median(vals) if vals else None), sorted(vals)


def verdict(gate: dict, records: list[dict], baseline: list[dict] | None) -> list[dict]:
    """One row per check: the median that was measured, what it was compared to, and pass/fail."""
    rows = []
    for chk in gate.get("checks") or []:
        got, spread = medians(records, chk["metric"])
        row = {"metric": chk["metric"], "op": chk["op"], "got": got, "spread": spread}
        if "value" in chk:
            row["want"] = chk["value"]
            row["pass"] = None if got is None else OPS[chk["op"]](got, chk["value"])
        else:
            base, _ = medians(baseline or [], chk["metric"])
            margin = chk.get("margin", 0) or 0
            row["baseline"] = base
            if got is None or base is None:
                row["pass"] = None
                row["want"] = f"{chk['op']} baseline"
            elif chk["op"] == "not_worse_than":
                row["want"] = round(base - margin, 6)
                row["pass"] = got >= base - margin
            elif chk["op"] == "not_above":
                row["want"] = round(base + margin, 6)
                row["pass"] = got <= base + margin
            else:
                row["want"] = base
                row["pass"] = OPS[chk["op"]](got, base)
        rows.append(row)
    return rows


def report(cfg: dict, done: list[dict]) -> str:
    """One markdown table per group: every level's median for every gate, and the verdict."""
    by = {}
    for r in done:
        by.setdefault((r["level"], r["gate"]), []).append(r)
    base_of = {g: lid for lid, lvl in cfg["levels"].items() for g in lvl.get("baseline_for", [])}
    out = [f"# Run F gates ({time.strftime('%Y-%m-%d %H:%M')} UTC)", "",
           "Medians over the runs recorded in `runs/gates/results.jsonl`; spread in brackets. "
           "`baseline` is the level a group is compared against (TRAINING_PLAN §6).", ""]
    failures, pending, blocked = [], [], {}
    for group in dict.fromkeys(g["group"] for g in cfg["gates"]):
        out += [f"## {group}", ""]
        base_level = base_of.get(group)
        for gate in [g for g in cfg["gates"] if g["group"] == group]:
            out.append(f"### {gate['id']} — {gate.get('title', '')}")
            if gate.get("manual"):
                out += ["", "Judged by a human; not run here.", ""]
                pending.append(f"{group}/{gate['id']} (manual)")
                continue
            baseline = by.get((base_level, gate["id"])) if base_level else None
            out += ["", "| level | " + " | ".join(gate.get("metrics", {})) + " | verdict |",
                    "|---" * (len(gate.get("metrics", {})) + 2) + "|"]
            for lid in cfg["levels"]:
                recs = by.get((lid, gate["id"]))
                if not recs:
                    continue
                cells = []
                for m in gate.get("metrics", {}):
                    med, sp = medians(recs, m)
                    cells.append("n/a" if med is None else
                                 (f"{med:g}" if len(set(sp)) <= 1 else f"{med:g} [{min(sp):g}–{max(sp):g}]"))
                if gate.get("report_only"):
                    v = "info"
                else:
                    rows = verdict(gate, recs, baseline)
                    if lid == base_level:
                        v = "baseline"
                    elif not rows:
                        v = "info"
                    elif any(r["pass"] is None for r in rows):
                        v = "PENDING"
                        pending.append(f"{group}/{gate['id']}/{lid}")
                    elif all(r["pass"] for r in rows):
                        v = "PASS"
                    else:
                        v = "**FAIL (blocks shipping)**" if gate.get("blocking") else "**FAIL**"
                        for r in rows:
                            if r["pass"] is False:
                                failures.append(f"{group}/{gate['id']}/{lid}: {r['metric']} "
                                                f"{r['got']} {r['op']} {r['want']}")
                                if gate.get("blocking"):
                                    blocked.setdefault(lid, []).append(f"{gate['id']} ({r['metric']} {r['got']})")
                cells.append(v)
                out.append(f"| {lid} | " + " | ".join(str(c) for c in cells) + " |")
            out.append("")
    head = ["## Summary", ""]
    head += [f"- FAIL: {len(failures)}", f"- not yet measured: {len(pending)}", ""]
    head += ship_decision(cfg, blocked, pending)
    head += (["Failures:", ""] + [f"- {f}" for f in failures] + [""]) if failures else []
    head += (["Not measured:", ""] + [f"- {p}" for p in pending] + [""]) if pending else []
    return "\n".join(out[:2] + head + out[2:]) + "\n"


def ship_decision(cfg: dict, blocked: dict, pending: list) -> list[str]:
    """Apply TRAINING_PLAN §6a: an epoch that fails a `blocking` gate cannot ship, whatever its speech numbers are.

    Reported, never enforced silently: the owner picks the adapter, this only states what the measured gates allow.
    """
    epochs = [lid for lid in cfg["levels"] if lid in ("f-e1", "f-e2")]
    if not epochs:
        return []
    out = ["### Kept abilities (TRAINING_PLAN §6a: blocking)", ""]
    for lid in epochs:
        why = blocked.get(lid)
        unmeasured = [p for p in pending if p.endswith(f"/{lid}") or "(manual)" in p]
        if why:
            out.append(f"- **{lid}: cannot ship** — failed {', '.join(why)}")
        elif unmeasured:
            out.append(f"- {lid}: no blocking failure so far, but {len(unmeasured)} kept-ability check(s) not measured")
        else:
            out.append(f"- {lid}: passes every blocking gate")
    e1, e2 = blocked.get("f-e1"), blocked.get("f-e2")
    if e2 and not e1:
        out += ["", "**Rule 2 applies: ship epoch 1.** Epoch 2 failed a kept-ability gate and epoch 1 did not."]
    elif e1 and e2:
        out += ["", "**Rule 3: both epochs fail kept abilities.** Evaluate the split stack (§7a) before the §7 "
                    "rollback — `herald-f` for extraction and photos, untuned `qwen3vl-fp8` for rerank / figures / "
                    "translation via `HERALD_KNOWLEDGE_MODEL`, both at `--gpu-memory-fraction ~0.30`. Measure free "
                    "memory with the app and Whisper up before choosing it."]
    return out + [""]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", default=None, help="comma-separated level ids (default: all, in config order)")
    ap.add_argument("--gates", default=None, help="comma-separated gate ids (default: all that apply)")
    ap.add_argument("--groups", default=None, help="comma-separated groups: speech, photos, kept")
    ap.add_argument("--runs", type=int, default=None, help="override the configured number of runs")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")
    ap.add_argument("--report-only", action="store_true", help="rebuild the report from results.jsonl")
    ap.add_argument("--force", action="store_true", help="rerun gates already in results.jsonl")
    ap.add_argument("--config", default=None, help="a gates.yaml other than config/gates.yaml")
    a = ap.parse_args()

    cfg = load_gates(Path(a.config) if a.config else None)
    runs = a.runs or cfg["runs"]
    res_path = ROOT / cfg["results"]
    res_path.parent.mkdir(parents=True, exist_ok=True)
    done = [json.loads(ln) for ln in res_path.read_text().splitlines() if ln.strip()] if res_path.exists() else []

    if not a.report_only:
        want_levels = a.levels.split(",") if a.levels else list(cfg["levels"])
        want_gates = set(a.gates.split(",")) if a.gates else None
        want_groups = set(a.groups.split(",")) if a.groups else None
        seen = {(r["level"], r["gate"], r["run"]) for r in done}
        for lid in want_levels:
            lvl = cfg["levels"][lid]
            todo = []
            for gate in cfg["gates"]:
                if want_gates and gate["id"] not in want_gates:
                    continue
                if want_groups and gate["group"] not in want_groups:
                    continue
                ok, why = applicable(gate, lvl)
                if ok:
                    todo.append(gate)
                elif not gate.get("manual"):
                    print(f"[skip] {lid}/{gate['id']}: {why}")
            if not todo:
                continue
            print(f"\n=== {lid} ({lvl['label']}): {len(todo)} gates x {runs} runs ===")
            if not a.dry_run and not served(cfg["endpoint"], lvl["label"]):
                print(f"  {lvl['label']} is not answering on {cfg['endpoint']}. Serve it, then rerun:\n"
                      f"      {serve_hint(lid, lvl)}")
                continue
            for gate in todo:
                print(f"  {gate['id']}")
                for run in range(1, runs + 1):
                    if not a.force and (lid, gate["id"], run) in seen:
                        print(f"    run {run}: already recorded")
                        continue
                    dump = ROOT / "eval" / "dumps" / "gates" / lid / f"{gate['id']}_run{run}.jsonl"
                    dump.parent.mkdir(parents=True, exist_ok=True)
                    rec = run_one(cfg, gate, lvl, run, dump, a.dry_run)
                    if a.dry_run:
                        break
                    rec = {"level": lid, "label": lvl["label"], **rec}
                    with open(res_path, "a") as fh:
                        fh.write(json.dumps(rec) + "\n")
                    done.append(rec)
                    print(f"    run {run}: exit {rec['exit']} in {rec['seconds']}s "
                          f"{rec.get('metrics') or rec.get('error', '')}")

    if a.dry_run:
        return
    md = ROOT / cfg["report_dir"] / "report.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(report(cfg, done))
    print(f"\nwrote {md}")


if __name__ == "__main__":
    main()
