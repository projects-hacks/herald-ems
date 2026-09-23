"""Read reviewed content from the repo's config/ directory (cached; content changes need a restart)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _path(rel: str) -> Path:
    p = (CONFIG_DIR / rel).resolve()
    if CONFIG_DIR.resolve() not in p.parents:
        raise ValueError(f"config path escapes config/: {rel}")
    return p


@lru_cache(maxsize=None)
def load_yaml(rel: str) -> Any:
    return yaml.safe_load(_path(rel).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_json(rel: str) -> Any:
    return json.loads(_path(rel).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_text(rel: str) -> str:
    return _path(rel).read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def load_jsonl(rel: str) -> tuple:
    return tuple(json.loads(line) for line in _path(rel).read_text(encoding="utf-8").splitlines() if line.strip())
