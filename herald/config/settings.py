"""Every runtime setting Herald reads from the environment, in one place (AGENTS.md rule 4).

Content (score tables, checklists, prompts, county rules) is not a setting: it lives in config/.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator

ROOT = Path(__file__).resolve().parents[2]
_LOCAL = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/|$)")


class Settings(BaseModel):
    # local model servers (inference never leaves this box: AGENTS.md invariant 1)
    llm_url: str = "http://127.0.0.1:8080/v1"
    llm_model: Optional[str] = None               # extraction model label; None = first model the server lists
    vision_model: Optional[str] = "qwen3vl-fp8"   # photo reading needs a vision model (the fine-tune is text-only)
    knowledge_model: Optional[str] = None         # split stack (TRAINING_PLAN §7a): the label that does protocol
                                                  # reranking, figure transcription and translation. None (default) =
                                                  # the same client as photo reading, which is today's single-model
                                                  # stack. Set it only when a fine-tune wins speech and photos but
                                                  # loses the base model's kept abilities. One URL serves both: the
                                                  # ZRT proxy routes by label on 127.0.0.1:8080 (proxy.json), so no
                                                  # second endpoint setting is needed.
    metrics_url: str = "http://127.0.0.1:8080/metrics"
    finetuned_models: tuple[str, ...] = ("ems",)  # labels that take the fine-tuned prompt (plus any "ems-*")
    stt_model: str = "openai/whisper-large-v3-turbo"
    warm_stt: bool = True
    stt_preload: bool = False                     # load Whisper before serving (demo): memory claimed up front, a
                                                  # failed load stops startup (docs/MEMORY_SAFETY.md)
    models_offline: bool = True                   # load local models from their folders; never contact a model hub
    # patient state
    auto_confirm: Optional[float] = None        # None = config/confirmation.yaml (calibrated per model)
    # speech extraction policy (MODEL_PLAN §0f; defaults keep the reviewed behavior until the team lead decides)
    guard_policy: str = "unconfirm"             # unconfirm (team lead, 2026-09-24): the model reads flagged speech,
                                                # every fact from it waits for a tap | skip_model (previous)
    reassess_min: Optional[int] = None            # None = the county's interval
    timezone: str = "America/Los_Angeles"
    county: str = "santa_clara"
    dispatch: Optional[str] = "possible stroke"
    unit_id: Optional[str] = None                 # this vehicle's unit ID, e.g. "Medic 25" (Policy 501 §III.A.1.a)
    # relay and demo link emulation
    ed_url: Optional[str] = None
    toxiproxy_url: str = "http://127.0.0.1:8474"
    # serving
    ui: str = "new"                               # "classic" serves web/ at / as well
    root: Path = ROOT                             # the repo: web/, ui/dist/
    data_dir: Optional[Path] = None               # captured audio and photos (default: <root>/data)
    # protocol lookup (P9): build the county knowledge base (embeddings on CPU, cached per document version)
    knowledge: bool = True
    protocol_mirror: Optional[str] = None        # base URL of a document mirror: <mirror>/<county>/<doc_id>.pdf
    # drug and allergen names -> RxNorm (S6); the index is built by scripts/build_rxnorm_index.py
    terminology: bool = True
    # memory guard (scripts/memguard.py) status, shown in /api/health
    memguard_status: Path = Path.home() / ".local/state/herald/memguard.json"
    memguard_stale_s: float = 5.0                 # heartbeat older than this = the guard is not running
    # cost-comparison overrides (defaults in config/telemetry.yaml)
    price_overrides: dict[str, float] = {}

    @field_validator("guard_policy")
    @classmethod
    def _guard(cls, v: str) -> str:
        if v not in ("skip_model", "unconfirm"):
            raise ValueError("HERALD_GUARD_POLICY must be skip_model or unconfirm")
        return v

    @field_validator("llm_url")
    @classmethod
    def _local_only(cls, v: str) -> str:
        if not _LOCAL.match(v):
            raise ValueError(f"HERALD_LLM_URL must point at this box, got {v}")
        return v.rstrip("/")

    @property
    def audio_dir(self) -> Path:
        return (self.data_dir or self.root / "data") / "audio"

    @property
    def protocols_dir(self) -> Path:
        return (self.data_dir or self.root / "data") / "protocols"

    @property
    def photo_dir(self) -> Path:
        return (self.data_dir or self.root / "data") / "photos"

    @property
    def terminology_index(self) -> Path:
        return (self.data_dir or self.root / "data") / "terminology" / "rxnorm_index.json"

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "Settings":
        e = dict(os.environ if env is None else env)

        def opt(name):
            return e.get(name) or None

        prices = {k: float(e[v]) for k, v in (("electricity_usd_per_kwh", "HERALD_PRICE_KWH"),
                                              ("cloud_llm_usd_per_1m_in", "HERALD_CLOUD_IN_PER_M"),
                                              ("cloud_llm_usd_per_1m_out", "HERALD_CLOUD_OUT_PER_M"),
                                              ("cloud_stt_usd_per_min", "HERALD_CLOUD_STT_PER_MIN")) if e.get(v)}
        fields = dict(
            llm_url=e.get("HERALD_LLM_URL", cls.model_fields["llm_url"].default),
            llm_model=opt("HERALD_LLM_MODEL"),
            vision_model=e.get("HERALD_VISION_MODEL", cls.model_fields["vision_model"].default) or None,
            knowledge_model=opt("HERALD_KNOWLEDGE_MODEL"),
            metrics_url=e.get("HERALD_ZRT_METRICS", cls.model_fields["metrics_url"].default),
            finetuned_models=tuple(m.strip() for m in e.get("HERALD_FINETUNED_MODELS", "ems").split(",") if m.strip()),
            stt_model=e.get("HERALD_STT_MODEL", cls.model_fields["stt_model"].default),
            warm_stt=e.get("HERALD_WARM_STT", "1") == "1",
            stt_preload=e.get("HERALD_STT_PRELOAD", "0") == "1",
            models_offline=e.get("HERALD_MODELS_OFFLINE", "1") == "1",
            auto_confirm=float(e["HERALD_AUTO_CONFIRM"]) if e.get("HERALD_AUTO_CONFIRM") else None,
            guard_policy=e.get("HERALD_GUARD_POLICY", "unconfirm"),
            reassess_min=int(e["HERALD_REASSESS_MIN"]) if e.get("HERALD_REASSESS_MIN") else None,
            timezone=e.get("HERALD_TZ", cls.model_fields["timezone"].default),
            county=e.get("HERALD_COUNTY", cls.model_fields["county"].default),
            dispatch=e.get("HERALD_DISPATCH", "possible stroke"),
            unit_id=opt("HERALD_UNIT_ID"),
            ed_url=opt("HERALD_ED_URL"),
            toxiproxy_url=e.get("TOXIPROXY_URL", cls.model_fields["toxiproxy_url"].default),
            ui=e.get("HERALD_UI", "new"),
            data_dir=Path(e["HERALD_DATA_DIR"]) if e.get("HERALD_DATA_DIR") else None,
            knowledge=e.get("HERALD_KNOWLEDGE", "1") == "1",
            protocol_mirror=opt("HERALD_PROTOCOL_MIRROR"),
            terminology=e.get("HERALD_TERMINOLOGY", "1") == "1",
            memguard_status=Path(e["HERALD_MEMGUARD_STATUS"]) if e.get("HERALD_MEMGUARD_STATUS")
            else cls.model_fields["memguard_status"].default,
            memguard_stale_s=float(e.get("HERALD_MEMGUARD_STALE_S") or 5.0),
            price_overrides=prices,
        )
        return cls(**fields)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once. Tests and tools build their own Settings and pass them in."""
    return Settings.from_env()
