"""Client for the local model server (ZRT / vLLM, OpenAI-compatible, on this box only: invariant 1)."""
from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx

from ..core.ports import UsageRecorder
from ..egress import EgressPolicy
from ..telemetry import tracking


class LocalLLMClient:
    """The `TextModel` interface. `model` pins a served label; otherwise the first label the server lists.

    `egress` (optional) is the one decision point (herald/egress/policy.py, E1) every request here is recorded
    against, even though `base_url` is already checked local-only above: every model call counts toward the same
    local-call total GET /api/egress reports, instead of local inference being invisible to that count.
    """

    def __init__(self, base_url: str, model: Optional[str] = None, usage: Optional[UsageRecorder] = None,
                 timeout: float = 60.0, availability_ttl: float = 5.0, egress: Optional[EgressPolicy] = None):
        if not re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)", base_url):
            raise RuntimeError(f"the model server must be on this box, got {base_url}")
        self.base_url = base_url.rstrip("/")
        self.pinned = model
        self.usage = usage
        self.timeout = timeout
        self.availability_ttl = availability_ttl
        self.egress = egress
        self._served: tuple[float, list[str]] = (float("-inf"), [])

    def served(self) -> list[str]:
        """The labels the server lists right now (cached for `availability_ttl` seconds); [] if it's unreachable."""
        checked, labels = self._served
        if time.monotonic() - checked > self.availability_ttl:
            try:
                if self.egress:
                    self.egress.decide(self.base_url, purpose="model:list")
                r = httpx.get(f"{self.base_url}/models", timeout=2.0)
                r.raise_for_status()
                labels = [m["id"] for m in r.json().get("data", [])]
            except Exception:
                labels = []
            self._served = (time.monotonic(), labels)
        return labels

    def model_name(self) -> Optional[str]:
        """The pinned label (even if it isn't served, so the screen can name what's missing), else the first served."""
        if self.pinned:
            return self.pinned
        labels = self.served()
        return labels[0] if labels else None

    def available(self) -> bool:
        """True only when the server is up and actually serving this label."""
        labels = self.served()
        return (self.pinned in labels) if self.pinned else bool(labels)

    def chat_json(self, system: str, user: str, *, image_b64: Optional[str] = None, max_tokens: int = 256,
                  schema: Optional[dict] = None, usage: Optional[dict] = None,
                  examples: Optional[list[tuple[str, str]]] = None, logprobs: bool = False,
                  top_logprobs: int = 0) -> dict:
        """One chat call that must return a JSON object. Reasoning is switched off. With `logprobs`, the returned
        dict also carries `_content` (the raw text) and `_tokens` ([(token, logprob, [(alternative, logprob)])]) for
        confidence scoring; the alternatives are the `top_logprobs` most likely tokens at each position."""
        model = self.model_name()
        if not model:
            raise RuntimeError("no local model is being served (check `zrt status`)")
        if self.egress:
            self.egress.decide(self.base_url, purpose="model:chat")
        content: list | str = user
        if image_b64:
            content = [{"type": "text", "text": user},
                       {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]
        body = {
            "model": model, "temperature": 0, "max_tokens": max_tokens,
            "messages": ([{"role": "system", "content": system}]
                         + [m for u, a in (examples or []) for m in ({"role": "user", "content": u},
                                                                     {"role": "assistant", "content": a})]
                         + [{"role": "user", "content": content}]),
            # strict schema: grammar-constrained from the first token; otherwise JSON mode
            "response_format": ({"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
                                if schema else {"type": "json_object"}),
            "chat_template_kwargs": {"enable_thinking": False},
            **({"logprobs": True} if logprobs else {}),
            **({"top_logprobs": top_logprobs} if logprobs and top_logprobs else {}),
        }
        with tracking(self.usage, "vision" if image_b64 else "text"):
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, timeout=self.timeout)
            r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        if self.usage:
            self.usage.record_llm(u, kind="vision" if image_b64 else "text")
        if usage is not None:
            usage.update(u)
        text = data["choices"][0]["message"]["content"] or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        m = re.search(r"\{.*\}", text, flags=re.S)
        try:
            out = json.loads(m.group(0) if m else text)
        except json.JSONDecodeError:
            out = salvage(text)
        if logprobs:
            lp = (data["choices"][0].get("logprobs") or {}).get("content") or []
            out["_content"] = data["choices"][0]["message"]["content"] or ""
            out["_tokens"] = [(t["token"], t["logprob"], [(a["token"], a["logprob"]) for a in t.get("top_logprobs") or []])
                              for t in lp]
        return out


def salvage(text: str) -> dict:
    """Output cut off at max_tokens: keep every complete [..] fact before the cut, drop the rest."""
    facts = []
    for m in re.finditer(r"\[\s*\"[a-z0-9_.]+\"\s*,.*?\](?=\s*[,\]])", text):
        try:
            row = json.loads(m.group(0))
            if isinstance(row, list):
                facts.append(row)
        except json.JSONDecodeError:
            continue
    if not facts:
        raise json.JSONDecodeError("unrecoverable model output", text, 0)
    return {"f": facts, "_salvaged": True}
