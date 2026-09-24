"""The composition root: builds every dependency once and wires them together (AGENTS.md rule 4).

Tests and tools pass their own Settings and fakes (e.g. a stub TextModel) to `build_context`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from zoneinfo import ZoneInfo

from ..checklists import ChecklistEngine
from ..config import Settings, get_settings
from ..config.county import CountyRegistry
from ..core.confirmation import ConfirmationPolicy
from ..core.incident import Incident
from ..core.ports import Normalizer, PhotoReader, SpeechToText, TextModel
from ..core.snapshot import Projector
from ..core.trends import TrendRules
from ..core.vocabulary import Vocabulary, default_vocabulary
from ..extraction import ModelExtractor
from ..extraction.guard import InstructionGuard, default_guard
from ..knowledge import KnowledgeService
from ..knowledge.rerank import LLMReranker
from ..models import LocalLLMClient, VisionReader, WhisperSTT
from ..relay import LinkEmulator, Relay, RelayTiers, default_tiers
from ..scoring import ScaleRegistry, default_scales
from ..telemetry import Telemetry
from ..terminology import MedicationCoder, build_coder
from .contract import UIContract
from .trace import TraceRecorder


@dataclass
class AppContext:
    settings: Settings
    vocab: Vocabulary
    scales: ScaleRegistry
    counties: CountyRegistry
    checklists: ChecklistEngine
    projector: Projector
    policy: ConfirmationPolicy
    tiers: RelayTiers
    trends: TrendRules
    guard: InstructionGuard
    telemetry: Telemetry
    text_model: TextModel          # extraction
    vision_model: TextModel        # photo reading
    stt: SpeechToText
    vision: PhotoReader
    model_extractor: ModelExtractor
    tracer: TraceRecorder
    contract: UIContract
    link: LinkEmulator
    coder: Optional[MedicationCoder] = None      # drug names -> RxNorm; None when the index isn't built
    relay: Optional[Relay] = None
    knowledge: Optional[KnowledgeService] = None
    incident: Optional[Incident] = None
    netem_mode: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def new_incident(self, dispatch: Optional[str]) -> Incident:
        self.incident = Incident(dispatch, vocabulary=self.vocab, policy=self.policy, projector=self.projector)
        return self.incident

    def full_state(self) -> dict:
        snap = self.incident.snapshot()
        rs = self.relay.status()
        snap["relay"], snap["ed_sync"], snap["netem"] = rs, rs["sync"], self.netem_mode
        if self.knowledge is not None:
            snap["protocols"] = self.knowledge.status()
        return snap


def build_context(settings: Optional[Settings] = None, *, text_model: Optional[TextModel] = None,
                  vision_model: Optional[TextModel] = None, stt: Optional[SpeechToText] = None,
                  vision: Optional[PhotoReader] = None, telemetry: Optional[Telemetry] = None,
                  embedder=None, protocol_fetch=None, normalizer: Optional[Normalizer] = None) -> AppContext:
    s = settings or get_settings()
    vocab, scales, tiers, guard = default_vocabulary(), default_scales(), default_tiers(), default_guard()
    counties = CountyRegistry(s.county)
    checklists = ChecklistEngine.from_config(counties)
    trends = TrendRules.from_config()
    projector = Projector(vocab, scales, checklists, counties, trends, ZoneInfo(s.timezone), s.reassess_min)
    tel = telemetry or Telemetry(s.metrics_url, s.price_overrides)
    model = text_model or LocalLLMClient(s.llm_url, s.llm_model, usage=tel)
    seeing = vision_model or (text_model if text_model is not None else LocalLLMClient(s.llm_url, s.vision_model, usage=tel))
    coder = build_coder(s, vocab, normalizer)
    model_extractor = ModelExtractor(model, vocabulary=vocab, finetuned_labels=s.finetuned_models, coder=coder)
    ctx = AppContext(
        settings=s, vocab=vocab, scales=scales, counties=counties, checklists=checklists, projector=projector,
        policy=ConfirmationPolicy(vocab, s.auto_confirm), tiers=tiers, trends=trends, guard=guard, telemetry=tel,
        text_model=model, vision_model=seeing, stt=stt or WhisperSTT(s.stt_model, usage=tel, offline=s.models_offline),
        vision=vision or VisionReader(seeing, coder),
        model_extractor=model_extractor,
        tracer=TraceRecorder(vocab, tiers),
        contract=UIContract(vocab, tiers, trends, checklists, counties, scales),
        link=LinkEmulator(s.toxiproxy_url), coder=coder)
    ctx.new_incident(s.dispatch)
    ctx.relay = Relay(lambda: ctx.incident, s.ed_url, tiers=tiers, scales=scales, audio_dir=s.audio_dir)
    if s.knowledge:
        if embedder is None and text_model is None:        # real deployment; tests pass their own (or none)
            from ..config import load_yaml
            from ..models.embedder import HFEmbedder
            e = load_yaml("knowledge.yaml")["embedding"]
            embedder = HFEmbedder(e["model"], e["query_prefix"], e["device"], offline=s.models_offline)
        ctx.knowledge = KnowledgeService(lambda: counties.active, s.protocols_dir, ctx.relay.link_state,
                                         embedder=embedder or None, reranker=LLMReranker(seeing), vision=seeing,
                                         fetch=protocol_fetch, mirror=s.protocol_mirror)
    return ctx
