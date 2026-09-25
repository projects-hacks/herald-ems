"""The composition root: builds every dependency once and wires them together (AGENTS.md rule 4).

Tests and tools pass their own Settings and fakes (e.g. a stub TextModel) to `build_context`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from ..checklists import ChecklistEngine
from ..config import Settings, get_settings
from ..config.county import CountyRegistry
from ..core.confirmation import ConfirmationPolicy
from ..core.corroboration import BatchConfirmation, CorroborationRules
from ..core.incident import Incident
from ..core.schema import Fact
from ..core.ports import Normalizer, PhotoReader, SpeechToText, TextModel
from ..core.roster import PatientRoster
from ..core.snapshot import Projector
from ..core.trends import TrendRules
from ..core.vocabulary import Vocabulary, default_vocabulary
from ..egress import EgressPolicy, default_policy
from ..extraction import ModelExtractor
from ..extraction.guard import InstructionGuard, default_guard
from ..knowledge import KnowledgeService
from ..knowledge.cues import ProtocolCues
from ..knowledge.rerank import LLMReranker
from ..models import LocalLLMClient, VisionReader, WhisperSTT
from ..relay import LinkEmulator, Relay, RelayTiers, default_tiers
from ..reporting import LINE_KINDS, FhirExport, HandoffBuilder, HandoffConfig, default_handoff_config
from ..scoring import ScaleRegistry, default_scales
from ..telemetry import Telemetry
from ..terminology import MedicationCoder, build_coder
from .contract import UIContract
from .media import dispose_incident_media
from .persistence import IncidentStore
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
    knowledge_model: TextModel     # protocol reranking, figure transcription, translation (S3). The same object as
                                   # vision_model unless settings.knowledge_model names a separate label (§7a)
    stt: SpeechToText
    vision: PhotoReader
    model_extractor: ModelExtractor
    tracer: TraceRecorder
    contract: UIContract
    link: LinkEmulator
    handoff: HandoffBuilder
    egress: EgressPolicy           # E1: the one decision point every outbound HTTP call passes through
    coder: Optional[MedicationCoder] = None      # drug names -> RxNorm; None when the index isn't built
    relay: Optional[Relay] = None
    knowledge: Optional[KnowledgeService] = None
    cues: Optional[ProtocolCues] = None           # the county passage for the situation Herald recognises
    fhir: Optional[FhirExport] = None
    roster: Optional[PatientRoster] = None
    netem_mode: Optional[str] = None
    persistence: Optional[IncidentStore] = None
    extra: dict = field(default_factory=dict)
    capture_agent: object = None
    evidence_dir: Optional[Path] = None      # where agentic capture keeps redacted stills (deleted with the call)
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
        self.restored = False
        patient = self.roster.add("Patient 1")
        if self.capture_agent is not None:
            self.capture_agent.patient_changed()
        return patient

    def end_incident(self) -> dict:
        cleanups = {
            inc.id: dispose_incident_media(inc, audio_dir=self.settings.audio_dir,
                                           photo_dir=self.settings.photo_dir, evidence_dir=self.evidence_dir)
            for inc in self.roster.incidents()
        }
        result = {
            "at": max(row["at"] for row in cleanups.values()),
            "deleted": {kind: sorted(media_id for row in cleanups.values() for media_id in row["deleted"][kind])
                        for kind in ("audio", "photo")},
            "missing": {kind: sorted(media_id for row in cleanups.values() for media_id in row["missing"][kind])
                        for kind in ("audio", "photo")},
            "invalid": {kind: sorted(media_id for row in cleanups.values() for media_id in row["invalid"][kind])
                        for kind in ("audio", "photo")},
            "patients": cleanups,
        }
        if self.persistence:
            self.persistence.discard()
        return result

    def persist(self) -> None:
        if not self.persistence:
            return
        patients = []
        for inc in self.roster.incidents():
            with inc.lock:
                patients.append({"id": inc.id, "label": inc.patient_label, "dispatch": inc.dispatch,
                                 "started": inc.started.isoformat(),
                                 "facts": [f.model_dump(mode="json") for f in inc.facts],
                                 "transcripts": inc.transcripts, "audit": inc.audit_log,
                                 "news2": inc.news2_history,
                                 "media_ids": {k: sorted(v) for k, v in inc.media_ids.items()}})
        self.persistence.save({"v": 1, "active": self.incident.id, "patients": patients,
                               "relay": {"authorized": self.relay.authorized, "acked": self.relay.acked,
                                         "ed_url": self.relay.ed_url}})

    def restore(self) -> bool:
        """Restore only an encrypted, unfinished call; corrupted state starts clean."""
        payload = self.persistence.load() if self.persistence else None
        if not payload or payload.get("v") != 1 or not payload.get("patients"):
            return False
        factory = self.roster._factory
        roster = PatientRoster(factory)
        for row in payload["patients"]:
            inc = factory()
            inc.id, inc.patient_label, inc.dispatch = row["id"], row.get("label"), row.get("dispatch")
            inc.started = datetime.fromisoformat(row["started"])
            inc.facts = [Fact.model_validate(fact) for fact in row.get("facts", [])]
            inc.transcripts, inc.audit_log = row.get("transcripts", []), row.get("audit", [])
            inc.news2_history = row.get("news2", [])
            inc.media_ids = {"audio": set(), "photo": set()} | {kind: set(ids) for kind, ids in row.get("media_ids", {}).items()}
            roster._incidents[inc.id], roster._labels[inc.id] = inc, inc.patient_label
        roster.active_id = payload.get("active") if payload.get("active") in roster._incidents else next(iter(roster._incidents))
        self.roster = roster
        relay = payload.get("relay", {})
        self.relay.ed_url, self.relay.authorized, self.relay.acked = relay.get("ed_url"), relay.get("authorized"), relay.get("acked", {})
        return True

    def pre_alert_scope(self) -> tuple[str, list[str]]:
        """The medic-facing label and the checklist alert ids actually open right now (`config/relay.yaml`
        `scopes` maps each id to what it may send). Authorization never relies on caller-provided wording or scope:
        both come from the checklist truthfully, every time."""
        readiness = self.incident.snapshot()["readiness"]
        labels, alert_ids = [row["label"] for row in readiness], [row["id"] for row in readiness]
        label = f"{' + '.join(labels)} pre-alert set" if labels else "patient update set"
        return label, alert_ids

    def full_state(self) -> dict:
        snap = self.incident.snapshot()
        snap["patients"] = self.roster.summaries()
        snap["restored"] = bool(getattr(self, "restored", False))
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
        if self.cues is not None:
            snap["protocol_cues"] = self.cues.view(snap)
        # E1: the real, measured decision (herald/egress/policy.py), not a literal -- core/snapshot.py has no I/O
        # and cannot know it, so the composition root fills it in here, the same way relay/protocols are merged in.
        egress_snapshot = self.egress.snapshot()
        snap["counters"]["cloud_ai_calls"] = egress_snapshot["cloud_ai_calls"]
        snap["counters"]["cloud_calls_refused"] = egress_snapshot["cloud_calls_refused"]
        return snap


def build_handoff(config: HandoffConfig, vocab: Vocabulary, scales: ScaleRegistry, checklists: ChecklistEngine,
                  settings: Settings) -> HandoffBuilder:
    """The handoff report builder; refuses to start on content that doesn't match the vocabulary or scores."""
    problems = config.problems(vocab, scales, LINE_KINDS, checklists.ids())
    if problems:
        raise ValueError("config/handoff.yaml: " + "; ".join(problems))
    return HandoffBuilder(config, vocab, scales, ZoneInfo(settings.timezone), settings.unit_id)


def build_context(settings: Optional[Settings] = None, *, text_model: Optional[TextModel] = None,
                  vision_model: Optional[TextModel] = None, knowledge_model: Optional[TextModel] = None,
                  stt: Optional[SpeechToText] = None,
                  vision: Optional[PhotoReader] = None, telemetry: Optional[Telemetry] = None,
                  embedder=None, protocol_fetch=None, normalizer: Optional[Normalizer] = None) -> AppContext:
    s = settings or get_settings()
    vocab, scales, tiers, guard = default_vocabulary(), default_scales(), default_tiers(), default_guard()
    counties = CountyRegistry(s.county)
    checklists = ChecklistEngine.from_config(counties)
    trends = TrendRules.from_config()
    corroboration = CorroborationRules.from_config()
    problems = corroboration.problems(vocab)
    if problems:
        raise ValueError("config/corroboration.yaml: " + "; ".join(problems))
    batch = BatchConfirmation(vocab, corroboration)
    fhir = FhirExport.from_config(vocab, scales)
    fhir_problems = fhir.problems()
    if fhir_problems:
        raise ValueError("config/fhir_codes.yaml: " + "; ".join(fhir_problems))
    projector = Projector(vocab, scales, checklists, counties, trends, ZoneInfo(s.timezone), s.reassess_min, batch)
    tel = telemetry or Telemetry(s.metrics_url, s.price_overrides)
    egress = default_policy(s)
    model = text_model or LocalLLMClient(s.llm_url, s.llm_model, usage=tel, egress=egress)
    seeing = vision_model or (text_model if text_model is not None
                              else LocalLLMClient(s.llm_url, s.vision_model, usage=tel, egress=egress))
    # Split stack (TRAINING_PLAN §7a): reranking, figure transcription and translation can run on a different label
    # from photo reading, for when a fine-tune wins speech and photos but loses the base model's kept abilities.
    # Unset (the default and today's stack) it is the *same object* as `seeing`, so nothing about the single-model
    # path changes. Extraction (`model`) and photo reading (`seeing`) are never moved by this setting.
    knowing = knowledge_model or (LocalLLMClient(s.llm_url, s.knowledge_model, usage=tel, egress=egress)
                                  if s.knowledge_model else seeing)
    coder = build_coder(s, vocab, normalizer)
    model_extractor = ModelExtractor(model, vocabulary=vocab, finetuned_labels=s.finetuned_models, coder=coder)
    ctx = AppContext(
        settings=s, vocab=vocab, scales=scales, counties=counties, checklists=checklists, projector=projector,
        policy=ConfirmationPolicy(vocab, s.auto_confirm), tiers=tiers, trends=trends, guard=guard, telemetry=tel,
        text_model=model, vision_model=seeing, knowledge_model=knowing,
        stt=stt or WhisperSTT(s.stt_model, usage=tel, offline=s.models_offline),
        vision=vision or VisionReader(seeing, coder),
        model_extractor=model_extractor,
        tracer=TraceRecorder(vocab, tiers),
        contract=UIContract(vocab, tiers, trends, checklists, counties, scales),
        link=LinkEmulator(s.toxiproxy_url), egress=egress, coder=coder,
        handoff=build_handoff(default_handoff_config(), vocab, scales, checklists, s), fhir=fhir,
        persistence=IncidentStore(s.state_dir, s.state_key_path) if s.persistence else None)
    ctx.new_incident(s.dispatch)
    ctx.relay = Relay(lambda: ctx.roster.incidents(), s.ed_url, tiers=tiers, scales=scales, audio_dir=s.audio_dir,
                      egress=egress, ed_token=s.ed_token)
    ctx.restored = ctx.restore()
    if s.knowledge:
        if embedder is None and text_model is None:        # real deployment; tests pass their own (or none)
            from ..config import load_yaml
            from ..models.embedder import HFEmbedder
            e = load_yaml("knowledge.yaml")["embedding"]
            embedder = HFEmbedder(e["model"], e["query_prefix"], e["device"], offline=s.models_offline)
        ctx.knowledge = KnowledgeService(lambda: counties.active, s.protocols_dir, ctx.relay.link_state,
                                         embedder=embedder or None, reranker=LLMReranker(knowing), vision=knowing,
                                         fetch=protocol_fetch, mirror=s.protocol_mirror, egress=egress)
        ctx.cues = ProtocolCues(lambda: ctx.knowledge.kb if ctx.knowledge.ready else None,
                                lambda: counties.active["id"])
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
    ctx.evidence_dir = store.directory
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
