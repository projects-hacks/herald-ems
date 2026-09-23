"""Local LLM client (ZRT / vLLM, OpenAI-compatible, on this box only)."""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import httpx

from .telemetry import TELEMETRY

BASE_URL = os.getenv("HERALD_LLM_URL", "http://127.0.0.1:8080/v1")
# Invariant: inference is local. Refuse any model endpoint that isn't on this machine.
if not re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/", BASE_URL):
    raise RuntimeError(f"HERALD_LLM_URL must point at this box, got {BASE_URL}")
_model_cache: Optional[str] = None


def model_name() -> Optional[str]:
    global _model_cache
    if os.getenv("HERALD_LLM_MODEL"):
        return os.getenv("HERALD_LLM_MODEL")
    if _model_cache:
        return _model_cache
    try:
        r = httpx.get(f"{BASE_URL}/models", timeout=2.0)
        r.raise_for_status()
        data = r.json().get("data", [])
        _model_cache = data[0]["id"] if data else None
    except Exception:
        _model_cache = None
    return _model_cache


def available() -> bool:
    return model_name() is not None


def chat_json(system: str, user: str, *, image_b64: Optional[str] = None,
              max_tokens: int = 256, timeout: float = 60.0, schema: Optional[dict] = None,
              usage: Optional[dict] = None, examples: Optional[list[tuple[str, str]]] = None) -> dict:
    """One chat call that must return a JSON object. Reasoning is switched off."""
    model = model_name()
    if not model:
        raise RuntimeError("no local LLM is being served (check `zrt status`)")
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
        # strict JSON schema: grammar-constrained from the first token (no <think>, no prose).
        "response_format": ({"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
                            if schema else {"type": "json_object"}),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    r = httpx.post(f"{BASE_URL}/chat/completions", json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    TELEMETRY.record_llm(data.get("usage") or {}, kind="vision" if image_b64 else "text")
    if usage is not None:
        usage.update(data.get("usage") or {})
    text = data["choices"][0]["message"]["content"] or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    try:
        return json.loads(m.group(0) if m else text)
    except json.JSONDecodeError:
        return _salvage(text)


def _salvage(text: str) -> dict:
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
