"""Per-fact confidence from the model's own token probabilities.

A small model's self-reported confidence is close to chance, while token probabilities separate right from wrong
extractions far better (JMIR 2025: AUROC 0.87 vs 0.70). Each fact row in the model's JSON output is located in the
raw text; its confidence is the joint probability of the tokens that wrote it (key, value, and who), i.e. how sure
the model was of that whole row. The auto-confirm threshold is calibrated on the dev set (config/confirmation.yaml).
"""
from __future__ import annotations

import math


def row_spans(content: str) -> list[tuple[int, int]]:
    """Character spans of each fact row [..] inside {"f": [ ... ]} (rows are depth-2 arrays)."""
    spans, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(content):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
            if depth == 2:
                start = i
        elif ch == "]":
            if depth == 2 and start is not None:
                spans.append((start, i + 1))
                start = None
            depth -= 1
    return spans


def value_span(content: str, a: int, b: int) -> tuple[int, int]:
    """Within row [a, b): from the value to the end of `who`, leaving out the key name and the closing bracket.
    Those tokens carry which fact the model writes next and whether another follows (output order), not whether
    this fact is right: in the live test, "BP 182" scored 0.28 because systolic vs temperature was a toss-up for
    the first row, while "182" itself had p = 1.0 (MODEL_PLAN §0g)."""
    row = content[a:b]
    k = row.find('",')
    if not row.startswith('["') or k < 0:
        return a, b
    end = b - 1                                  # the closing ]
    if content[end - 1] == '"':
        end -= 1                                 # and who's closing quote (it's the '"]' vs '"],["' token)
    return a + k + 2, end


def _key_span(content: str, a: int) -> tuple[int, int]:
    """The key's characters inside row ["key", ...] starting at a, plus its closing quote (which decides where the
    key name ends, e.g. vitals.gcs vs vitals.gcs_motor). (-1, -1) if the row doesn't start with a string."""
    if not content.startswith('["', a):
        return -1, -1
    close = content.find('"', a + 2)
    return (a + 2, close + 1) if close >= 0 else (-1, -1)


def _order_free_key_logprob(content: str, ka: int, kb: int, offsets: list, later_keys: set) -> float:
    """Log-probability that the model meant to write this key here or later: at each token of the key, probability
    the model gave to alternatives that lead to a key it does write in this or a later row counts as agreement, not
    doubt. Probability on keys it never writes (a fact it considered and dropped, or a different fact) stays doubt."""
    total = 0.0
    for s, e, lp, alts in offsets:
        if not (s < kb and e > ka):
            continue
        choices = {tok: alp for tok, alp in alts}
        choices.setdefault(content[s:e], lp)
        mass = 0.0
        for tok, alp in choices.items():
            text = tok
            if s < ka:                                   # token also carries structure before the key ('["' + ...)
                if not tok.startswith(content[s:ka]):
                    continue
                text = tok[ka - s:]
            cand = content[ka:max(s, ka)] + text
            if '"' in cand:
                ok = cand.split('"', 1)[0] in later_keys
            else:
                ok = any(k.startswith(cand) for k in later_keys)
            if ok:
                mass += math.exp(alp)
        total += math.log(min(1.0, max(mass, 1e-12)))
    return total


def row_confidences(content: str, tokens: list, mode: str = "joint") -> list[float]:
    """Per-row confidence from the tokens that wrote each row, in output order. `tokens` are (token, logprob) or
    (token, logprob, [(alternative, logprob)]).
    joint = product over the whole row; value = product over value and who given the key (see value_span);
    order_free = value, times the key's probability with alternatives the model writes later counted as agreement
    (needs top alternatives); min = the row's weakest token; mean = geometric mean (length-normalized)."""
    offsets, pos = [], 0
    for t in tokens:
        tok, lp = t[0], t[1]
        offsets.append((pos, pos + len(tok), lp, t[2] if len(t) > 2 else []))
        pos += len(tok)
    spans = row_spans(content)
    keys = [content[ka:kb - 1] if ka >= 0 else None for ka, kb in (_key_span(content, a) for a, _ in spans)]
    out = []
    for i, (a, b) in enumerate(spans):
        extra = 0.0
        if mode in ("value", "order_free"):
            ka, kb = _key_span(content, a)
            if mode == "order_free" and ka >= 0:
                extra = _order_free_key_logprob(content, ka, kb, offsets, {k for k in keys[i:] if k})
            a, b = value_span(content, a, b)
        lps = [lp for s, e, lp, _ in offsets if s < b and e > a] or [float("-inf")]
        agg = {"joint": sum(lps), "value": sum(lps), "order_free": sum(lps) + extra,
               "min": min(lps), "mean": sum(lps) / len(lps)}[mode]
        out.append(math.exp(agg))
    return out
