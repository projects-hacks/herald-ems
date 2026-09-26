"""Who said it, from the words alone: the check step's `said_by` and `patient_name` (herald/extraction/verify.py).

The room microphone cannot tell voices apart, so Herald reads whose information each fact is from how it was said.
This benchmark gives the check step each utterance with its facts as proposals and no hint of who spoke, then scores
its answer per fact against the labeled role:

  correct     the role matches (a relationship word like "husband" counts as family or bystander, as the vocabulary
              groups it)
  unclear     the model declined to say; safe, the fact stays "speaker not identified"
  wrong       another role
  unsafe      someone else's information read as the medic's own report: the error that matters, because the
              medic's own report may confirm itself (config/confirmation.yaml room_mic)

Sets: gold_v1 and gold_v2 (100 utterances each, roles labeled by two annotators; mostly the medic's report, with
family, patient and bystander attributions), and live_speaker_v1 (our own room-microphone demo runs, 2026-09-26,
labeled by hand; garbled clips left out). The patient's name is scored on every utterance: found when the words state
it, and a false name when they don't.

    python eval/bench_speaker.py [--runs 3] [--sets gold_v1 gold_v2 live_speaker_v1] [--out eval/dumps/bench_speaker.json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from herald.core.schema import FactIn, Provenance  # noqa: E402
from herald.core.vocabulary import default_vocabulary  # noqa: E402
from herald.extraction.verify import MEDIC, PATIENT, FactVerifier  # noqa: E402
from herald.models.llm_client import LocalLLMClient  # noqa: E402

ROLES = ("medic", "patient", "family", "bystander")


def role_of(word: str | None, vocab) -> str | None:
    if word in (MEDIC, PATIENT):
        return word
    return vocab.speaker_role(word) if word else None


def score_set(name: str, verifier: FactVerifier, vocab) -> dict:
    rows = [json.loads(line) for line in (ROOT / "eval" / f"{name}.jsonl").open()]
    c: Counter = Counter()
    confusion: Counter = Counter()
    unsafe_examples, secs = [], []
    for row in rows:
        # the name is what the check step must find by itself, so a labeled name is never among the proposals
        want_name = row.get("patient_name") or next((v for k, v, _ in row["facts"] if k == "patient.name"), None)
        labeled = [x for x in row["facts"] if x[0] != "patient.name"]
        facts = [FactIn(key=k, value=v, provenance=Provenance(text=row["text"])) for k, v, _ in labeled]
        t = time.perf_counter()
        try:
            result = verifier.read(row["text"], facts)
        except Exception as e:                      # counted, never silently dropped
            c["errors"] += 1
            print(f"  {row['id']}: error {str(e)[:120]}", file=sys.stderr)
            continue
        secs.append(time.perf_counter() - t)
        for f, (_, _, gold) in zip(facts, labeled):
            got = role_of(f.provenance.heard_as, vocab) if f.provenance.checked else None
            c["facts"] += 1
            confusion[(gold, got or "unclear")] += 1
            if got is None:
                c["unclear"] += 1
            elif got == gold:
                c["correct"] += 1
            else:
                c["wrong"] += 1
                if got == MEDIC:
                    c["unsafe"] += 1
                    unsafe_examples.append({"id": row["id"], "key": f.key, "gold": gold, "text": row["text"][:140]})
            if gold != MEDIC:
                c["not_medic"] += 1
            else:
                c["medic"] += 1
                c["medic_found"] += got == MEDIC
        if not row.get("name_unscored"):
            want, got_name = want_name, result.patient_name
            if want:
                c["names"] += 1
                c["names_found"] += bool(got_name) and got_name.lower() == want.lower()
            elif got_name:
                c["false_names"] += 1
    n = c["facts"] or 1
    return {
        "utterances": len(rows), "facts": c["facts"], "errors": c["errors"],
        "correct": c["correct"], "unclear": c["unclear"], "wrong": c["wrong"],
        "accuracy_when_answered": round(c["correct"] / max(1, c["correct"] + c["wrong"]), 3),
        "correct_of_all": round(c["correct"] / n, 3),
        "unsafe": c["unsafe"], "not_medic_facts": c["not_medic"],
        "unsafe_rate": round(c["unsafe"] / max(1, c["not_medic"]), 3),
        "medic_facts": c["medic"], "medic_recognised": round(c["medic_found"] / max(1, c["medic"]), 3),
        "names": c["names"], "names_found": c["names_found"], "false_names": c["false_names"],
        "confusion": {f"{g}->{p}": k for (g, p), k in sorted(confusion.items())},
        "unsafe_examples": unsafe_examples,
        "seconds_median": round(statistics.median(secs), 2) if secs else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["gold_v1", "gold_v2", "live_speaker_v1"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="herald-f")
    ap.add_argument("--url", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--out", default=str(ROOT / "eval" / "dumps" / "bench_speaker.json"))
    a = ap.parse_args()
    vocab = default_vocabulary()
    verifier = FactVerifier(LocalLLMClient(a.url, model=a.model), vocab)
    out = {"model": a.model, "runs": []}
    for i in range(a.runs):
        run = {s: score_set(s, verifier, vocab) for s in a.sets}
        out["runs"].append(run)
        for s, r in run.items():
            print(f"run {i + 1} {s:16s} facts {r['facts']:3d}  correct {r['correct']:3d}  unclear {r['unclear']:3d}  "
                  f"wrong {r['wrong']:3d}  unsafe {r['unsafe']}/{r['not_medic_facts']}  "
                  f"medic recognised {r['medic_recognised']}  names {r['names_found']}/{r['names']} "
                  f"false names {r['false_names']}  errors {r['errors']}  {r['seconds_median']} s")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
