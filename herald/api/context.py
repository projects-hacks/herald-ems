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
from ..core.roster import PatientRoster
from ..core.snapshot import Projector
from ..core.trends import TrendRules
from ..core.vocabulary import Vocabulary, default_vocabulary
from ..extraction import ModelExtractor
from ..extraction.guard import InstructionGuard, default_guard
from ..knowledge import KnowledgeService
from ..knowledge.rerank import LLMReranker
from ..models import LocalLLMClient, VisionReader, WhisperSTT
from ..relay import LinkEmulator, Relay, RelayTiers, default_tiers
from ..reporting import LINE_KINDS, HandoffBuilder, HandoffConfig, default_handoff_config
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
    handoff: HandoffBuilder
    coder: Optional[MedicationCoder] = None      # drug names -> RxNorm; None when the index isn't built
    relay: Optional[Relay] = None
    knowledge: Optional[KnowledgeService] = None
    roster: Optional[PatientRoster] = None
    netem_mode: Optional[str] = None
    extra: dict = field(default_factory=dict)
    capture_agent: object = None
    frame_reader: object = None
    speech_in_flight: int = 0

    @property
    def incident(self) -> Incident:
        if self.roster is None:
            raise RuntimeError("patient roster is not initialized")
        return self.roster.active()

    def new_incident(self, dispatch: Optional[str]) -> Incident:
        def factory() -> Incident:
            return Incident(dispatch, vocabulary=self.vocab, policy=self.policy, projector=self.projector)

        self.roster = PatientRoster(factory)
        patient = self.roster.add("Patient 1")
        if self.capture_agent is not None:
            self.capture_agent.patient_changed()
        return patient

    def full_state(self) -> dict:
        snap = self.incident.snapshot()
        snap["patients"] = self.roster.summaries()
        snap["active_patient"] = self.incident.id
        snap["handoff"] = self.handoff.summary(self.handoff.build(self.incident, snapshot=snap))
        rs = self.relay.status()
        active_relay = rs["patients"].get(self.incident.id, {})
        snap["relay"], snap["ed_sync"], snap["netem"] = rs, active_relay.get("sync", {}), self.netem_mode
        if self.capture_agent is not None:
            self.capture_agent.patient_changed()
            snap["capture"] = self.capture_agent.status()
        if self.knowledge is not None:
            snap["protocols"] = self.knowledge.status()
        return snap


def build_handoff(config: HandoffConfig, vocab: Vocabulary, scales: ScaleRegistry, checklists: ChecklistEngine,
                  settings: Settings) -> HandoffBuilder:
    """The handoff report builder; refuses to start on content that doesn't match the vocabulary or scores."""
    problems = config.problems(vocab, scales, LINE_KINDS, checklists.ids())
    if problems:
        raise ValueError("config/handoff.yaml: " + "; ".join(problems))
    return HandoffBuilder(config, vocab, scales, ZoneInfo(settings.timezone), settings.unit_id)


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
        link=LinkEmulator(s.toxiproxy_url), coder=coder,
        handoff=build_handoff(default_handoff_config(), vocab, scales, checklists, s))
    ctx.new_incident(s.dispatch)
    ctx.relay = Relay(lambda: ctx.roster.incidents(), s.ed_url, tiers=tiers, scales=scales, audio_dir=s.audio_dir)
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


def wire_capture(ctx: AppContext, broadcast):
    """Compose the capture pipeline once. Construction loads no neural models or camera devices."""
    from copy import deepcopy
    from pathlib import Path
    from ..config import load_yaml
    from ..capture.agent import CaptureAgent
    from ..capture.config import validate_config
    from ..capture.privacy import EvidenceStore, FaceBlur
    from ..capture.reading import FrameReader
    from ..capture.sources import ReplayFrameSource
    from ..capture.verify import DrugCheck
    from .capture import CaptureService

    config = validate_config(deepcopy(load_yaml(ctx.settings.capture_config)))
    service = CaptureService(ctx, broadcast)
    blur = FaceBlur(config["privacy"])
    store = EvidenceStore(ctx.settings.photo_dir, config["privacy"], blur)
    ctx.frame_reader = FrameReader(config, lambda: ctx.incident, ctx.vision, store,
                                   DrugCheck(ctx.coder, config["verify"]), ctx.tracer,
                                   ctx.vision_model.model_name, broadcast)

    async def read(frame, intent, roi, valid):
        return await service.photo(frame.jpeg, intent.mode, auto=True, frame=frame, intent=intent, roi=roi, valid=valid)

    agent = CaptureAgent(config, read, incident_id=lambda: ctx.incident.id,
                         speech_busy=lambda: ctx.speech_in_flight > 0, source=ctx.settings.capture_source,
                         notify=broadcast, hold=lambda id, reason: ctx.incident.hold_verification(id, reason))
    agent.set_auto(ctx.settings.capture_auto and ctx.settings.capture_source != "off")
    ctx.capture_agent = agent
    service.listeners.append(agent)
    source = None
    if ctx.settings.capture_source.startswith("replay:"):
        source = ReplayFrameSource(Path(ctx.settings.capture_source.partition(":")[2]), config["fps_in"], config)
    return service, source
