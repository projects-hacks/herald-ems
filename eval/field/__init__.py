"""Field robustness evaluation (docs/TASK_SPECS.md S8): real people say fact cards in their own words, in quiet and
with road noise; the clips go through the product's speech-to-text and extractor and are scored against the card.

  cards.py      the fact cards (the gold) and which cards each speaker says
  manifest.py   the recordings manifest and the consent log
  scoring.py    per-clip scoring with the benchmark's own atoms (eval/bench_extract.py)
  stats.py      precision/recall/F1 and bootstrap confidence intervals
  recorder.py   the recording station (python -m eval.field.recorder --station <you> --port 8105)
"""
