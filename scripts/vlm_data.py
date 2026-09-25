"""Run F training data: rows, the epoch mix, prompt rendering and loss masks (scripts/train_vlm_lora.py).

Every row becomes the exact request `herald/models/llm_client.py` sends: a system message, then the user content as a
plain string (speech, rerank, translation) or as [text, image] in that order (photos, figures), with thinking off.
vLLM turns an OpenAI `image_url` part into an image placeholder in place (openai content format), so rendering the
same messages with the model's own chat template gives the same prompt tokens as serving. The answer is tokenized on
its own after `<|im_start|>assistant\\n`, as the served model generates it, and only its tokens (plus `<|im_end|>`)
carry loss. Nothing here knows any clinical key: targets are whatever the data rows say.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
END = "<|im_end|>"


@dataclass(frozen=True)
class Example:
    kind: str                      # text | image | replay
    system: str
    user: str
    assistant: str
    image: Optional[Path] = None
    id: str = ""
    task: str = ""                 # e.g. extract, monitor, rerank, figure, translate

    def messages(self) -> list[dict]:
        """The request as llm_client sends it (image_url -> {"type": "image"}, as vLLM passes it to the template)."""
        user = [{"type": "text", "text": self.user}, {"type": "image"}] if self.image else self.user
        return [{"role": "system", "content": self.system}, {"role": "user", "content": user}]


# ---------- rows ----------
def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type", "text") == "text")


def _image_of(content) -> Optional[str]:
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict) and p.get("type") in ("image", "image_url"):
                v = p.get("image") or p.get("path") or p.get("image_url")
                return v.get("url") if isinstance(v, dict) else v
    return None


def _answer(v) -> str:
    """A target as the model should write it: strings verbatim; JSON objects compact (fewer tokens = less latency)."""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _resolve(p: str, base: Path) -> Path:
    q = Path(p)
    if q.is_absolute():
        return q
    return (base / q) if (base / q).exists() else (ROOT / q)


def from_record(r: dict, kind: str, base: Path, default_system: Optional[str] = None,
                vision_prompts: Optional[dict] = None) -> Example:
    """One JSONL row in any of the accepted shapes (MODEL_PLAN §0l "Data formats")."""
    image = r.get("image") or r.get("image_path")
    if "messages" in r:
        msgs = r["messages"]
        system = next((_text_of(m["content"]) for m in msgs if m["role"] == "system"), default_system)
        user_msg = next(m for m in msgs if m["role"] == "user")
        user, image = _text_of(user_msg["content"]), image or _image_of(user_msg["content"])
        answer = next(m["content"] for m in reversed(msgs) if m["role"] == "assistant")
    elif "user" in r or "prompt" in r:
        system, user = r.get("system", default_system), r.get("user", r.get("prompt"))
        answer = next(r[k] for k in ("assistant", "target", "completion", "answer") if k in r)
    elif "text" in r and "completion" in r:                      # run E format: input lines + target
        system, user, answer = default_system, r["text"], r["completion"]
    elif image and vision_prompts and "mode" in r:               # photo row with only mode + target
        system, user = vision_prompts["system"], vision_prompts["modes"][r["mode"]]
        answer = next(r[k] for k in ("target", "assistant", "completion", "answer") if k in r)
    else:
        raise ValueError(f"unrecognized row shape: {sorted(r)}")
    if system is None:
        raise ValueError(f"row {r.get('id')} has no system prompt and no default was given")
    return Example(kind, system, user, _answer(answer), _resolve(image, base) if image else None,
                   str(r.get("id", "")), str(r.get("task") or r.get("mode") or ("extract" if kind == "text" else "")))


def load_rows(path: Path, kind: str, default_system: Optional[str] = None, vision_prompts: Optional[dict] = None,
              limit: Optional[int] = None) -> list[Example]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(from_record(json.loads(line), kind, path.parent, default_system, vision_prompts))
            if limit and len(out) >= limit:
                break
    return out


def prompt_drift(rows: Iterable[Example], expected: dict[str, set[str]]) -> dict[str, int]:
    """Rows whose system (or photo user) prompt differs from what the app sends today, per task. `expected` maps a
    task to the allowed prompt texts ("system" key for all rows). Training on a stale prompt would train one request
    and serve another."""
    bad: dict[str, int] = {}
    for ex in rows:
        ok_sys = expected.get("system:" + ex.kind)
        ok_user = expected.get("user:" + ex.task) if ex.image else None
        if (ok_sys is not None and ex.system not in ok_sys) or (ok_user is not None and ex.user not in ok_user):
            bad[ex.task or ex.kind] = bad.get(ex.task or ex.kind, 0) + 1
    return bad


# ---------- the epoch mix ----------
class Stream:
    """Rows without replacement: a fresh shuffle only once every row was used (epoch 2 sees new photos)."""

    def __init__(self, rows: list, rng: random.Random):
        self.rows, self.rng, self.queue = rows, rng, []

    def take(self, n: int) -> list:
        out = []
        while len(out) < n and self.rows:
            if not self.queue:
                fresh = self.rows[:]
                self.rng.shuffle(fresh)
                taken = {id(r) for r in out}            # rows already in this epoch come last: no repeats within it
                self.queue = [r for r in fresh if id(r) in taken] + [r for r in fresh if id(r) not in taken]
            out.append(self.queue.pop())
        return out


def mix_epochs(text: list, image: list, replay: list, mix: dict) -> list[list]:
    """Rows per epoch: every speech row (or `text_rows_per_epoch`), `image_rows_per_epoch` photos, and replay rows so
    that they are `replay_share` of the epoch."""
    rng = random.Random(mix.get("seed", 13))
    streams = [Stream(text, rng), Stream(image, rng), Stream(replay, rng)]
    n_text = len(text) if mix.get("text_rows_per_epoch", "all") == "all" else int(mix["text_rows_per_epoch"])
    n_img = min(int(mix.get("image_rows_per_epoch", len(image))), len(image))     # never oversampled
    share = float(mix.get("replay_share", 0.0))
    n_rep = min(round(share / (1 - share) * (n_text + n_img)), len(replay))     # never oversampled either
    epochs = []
    for _ in range(int(mix["epochs"])):
        rows = streams[0].take(n_text) + streams[1].take(n_img) + streams[2].take(n_rep)
        rng.shuffle(rows)
        epochs.append(rows)
    return epochs


# ---------- micro-batches ----------
def plan_batches(lengths: list[int], max_tokens: int, max_rows: int, accum: int, rng: random.Random) -> list[list[int]]:
    """Micro-batches of rows with similar length, padded size (rows x longest) within `max_tokens`, shuffled; the count
    is made a multiple of `accum` by splitting the largest batches, so every optimizer step (and the epoch's last one)
    has `accum` micro-batches and an epoch ends exactly on an optimizer step."""
    idx = list(range(len(lengths)))
    rng.shuffle(idx)
    chunk = max_rows * 50
    batches: list[list[int]] = []
    for c in range(0, len(idx), chunk):
        part = sorted(idx[c:c + chunk], key=lambda i: -lengths[i])
        cur: list[int] = []
        for i in part:
            longest = lengths[cur[0]] if cur else lengths[i]
            if cur and (len(cur) >= max_rows or (len(cur) + 1) * longest > max_tokens):
                batches.append(cur)
                cur = []
            cur.append(i)
        if cur:
            batches.append(cur)
    while len(batches) % accum:
        big = max((b for b in batches if len(b) > 1), key=len, default=None)
        if big is None:
            break                    # only single-row batches left: the last step is shorter (reported)
        batches.remove(big)
        batches += [big[: len(big) // 2], big[len(big) // 2:]]
    rng.shuffle(batches)
    return batches


def image_tokens(size: tuple[int, int], max_pixels: int, min_pixels: int, patch: int = 16, merge: int = 2) -> int:
    """Tokens an image becomes after the processor's resize (Qwen3-VL: one token per 32x32 pixels)."""
    from transformers.models.qwen2_vl.image_processing_qwen2_vl import smart_resize

    w, h = size
    rh, rw = smart_resize(h, w, factor=patch * merge, min_pixels=min_pixels, max_pixels=max_pixels)
    return (rh // patch) * (rw // patch) // (merge * merge)


# ---------- encoding ----------
class Encoder:
    """Tokenizes rows with the model's processor, the way vLLM formats the request."""

    def __init__(self, processor, max_pixels: int, min_pixels: int):
        self.processor = processor
        self.tok = getattr(processor, "tokenizer", processor)
        self.max_pixels, self.min_pixels = max_pixels, min_pixels
        ip = getattr(processor, "image_processor", None)
        if ip is not None:
            ip.size = {"longest_edge": max_pixels, "shortest_edge": min_pixels}
        self.image_pad = self.tok.convert_tokens_to_ids("<|image_pad|>")
        self.template = getattr(processor, "chat_template", None) or self.tok.chat_template
        self.pad_id = self.tok.pad_token_id if self.tok.pad_token_id is not None else self.tok.eos_token_id

    def prompt_text(self, ex: Example) -> str:
        """The chat template rendered as vLLM renders it (the processor's template: chat_template.json)."""
        return self.tok.apply_chat_template(ex.messages(), chat_template=self.template, tokenize=False,
                                            add_generation_prompt=True, enable_thinking=False)

    def answer_ids(self, ex: Example) -> list[int]:
        return self.tok(ex.assistant + END, add_special_tokens=False)["input_ids"]

    def encode(self, ex: Example) -> dict:
        text = self.prompt_text(ex)
        if ex.image is not None:
            from PIL import Image

            with Image.open(ex.image) as im:
                img = im.convert("RGB")
            enc = self.processor(text=[text], images=[img], return_tensors="pt")
        else:
            enc = {"input_ids": [self.tok(text, add_special_tokens=False)["input_ids"]]}
        prompt = [int(t) for t in enc["input_ids"][0]]
        answer = self.answer_ids(ex)
        ids = prompt + answer
        # which tokens are image patches (M-RoPE positions; what the processor returns as mm_token_type_ids)
        out = {"input_ids": ids, "labels": [-100] * len(prompt) + answer,
               "mm_token_type_ids": [1 if t == self.image_pad else 0 for t in ids]}
        if ex.image is not None:
            out["pixel_values"], out["image_grid_thw"] = enc["pixel_values"], enc["image_grid_thw"]
        return out

    def length(self, ex: Example) -> int:
        """Tokens of the row without decoding pixels (image size from the file header)."""
        n = len(self.tok(self.prompt_text(ex), add_special_tokens=False)["input_ids"]) + len(self.answer_ids(ex))
        if ex.image is not None:
            from PIL import Image

            with Image.open(ex.image) as im:
                n += image_tokens(im.size, self.max_pixels, self.min_pixels) - 1   # one <|image_pad|> expands
        return n


def collate(features: list[dict], pad_id: int) -> dict:
    import torch

    n = max(len(f["input_ids"]) for f in features)
    ids = torch.full((len(features), n), pad_id, dtype=torch.long)
    labels = torch.full((len(features), n), -100, dtype=torch.long)
    mask = torch.zeros((len(features), n), dtype=torch.long)
    for i, f in enumerate(features):
        k = len(f["input_ids"])
        ids[i, :k] = torch.tensor(f["input_ids"])
        labels[i, :k] = torch.tensor(f["labels"])
        mask[i, :k] = 1
    types = torch.zeros((len(features), n), dtype=torch.long)
    for i, f in enumerate(features):
        types[i, : len(f["input_ids"])] = torch.tensor(f.get("mm_token_type_ids", [0] * len(f["input_ids"])))
    out = {"input_ids": ids, "attention_mask": mask, "labels": labels, "mm_token_type_ids": types}
    pix = [f["pixel_values"] for f in features if "pixel_values" in f]
    if pix:
        out["pixel_values"] = torch.cat(pix, 0)
        out["image_grid_thw"] = torch.cat([f["image_grid_thw"] for f in features if "image_grid_thw" in f], 0)
    return out


def steps_for(batches_per_epoch: list[int], accum: int) -> list[int]:
    """Optimizer step at which each epoch ends."""
    ends, s = [], 0
    for b in batches_per_epoch:
        s += math.ceil(b / accum)
        ends.append(s)
    return ends
