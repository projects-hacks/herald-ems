"""Client for the local model server (ZRT / vLLM, OpenAI-compatible, on this box only: invariant 1)."""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from ..core.ports import UsageRecorder


class LocalLLMClient:
    """The `TextModel` interface. `model` pins a served label; otherwise the first label the server lists."""

    def __init__(self, base_url: str, model: Optional[str] = None, usage: Optional[UsageRecorder] = None,
                 timeout: float = 60.0):
        if not re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)", base_url):
            raise RuntimeError(f"the model server must be on this box, got {base_url}")
        self.base_url = base_url.rstrip("/")
        self.pinned = model
        self.usage = usage
        self.timeout = timeout
        self._discovered: Optional[str] = None

    def model_name(self) -> Optional[str]:
        if self.pinned:
            return self.pinned
        if self._discovered is None:
            try:
                r = httpx.get(f"{self.base_url}/models", timeout=2.0)
                r.raise_for_status()
                data = r.json().get("data", [])
                self._discovered = data[0]["id"] if data else None
            except Exception:
                return None
        return self._discovered

    def available(self) -> bool:
        return self.model_name() is not None

    def chat_json(self, system: str, user: str, *, image_b64: Optional[str] = None, max_tokens: int = 256,
                  schema: Optional[dict] = None, usage: Optional[dict] = None,
                  examples: Optional[list[tuple[str, str]]] = None) -> dict:
        """One chat call that must return a JSON object. Reasoning is switched off."""
        model = self.model_name()
        if not model:
            raise RuntimeError("no local model is being served (check `zrt status`)")
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
        }
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
            return json.loads(m.group(0) if m else text)
        except json.JSONDecodeError:
            return salvage(text)


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
