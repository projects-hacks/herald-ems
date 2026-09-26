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
from ..core.disposition import Dispositions
from ..core.incident import Incident
from ..core.ports import Normalizer, PhotoReader, Router, SpeechToText, TextModel
from ..core.schema import utcnow
from ..core.roster import PatientRoster
from ..core.snapshot import Projector
from ..core.trends import TrendRules
from ..core.vocabulary import Vocabulary, default_vocabulary
from ..egress import EgressPolicy, default_policy
from ..extraction import ModelExtractor
from ..extraction.guard import InstructionGuard, default_guard
from ..knowledge import KnowledgeService
from ..knowledge.cues import ProtocolCues
from ..knowledge.keypoints import KeyPointPicker
from ..extraction.verify import FactVerifier
from ..knowledge.rerank import LLMReranker
from ..models import LocalLLMClient, VisionReader, WhisperSTT
from ..relay import LinkEmulator, Relay, RelayTiers, default_tiers
from ..reporting import LINE_KINDS, FhirDocument, FhirExport, HandoffBuilder, HandoffConfig, default_handoff_config
from ..scoring import ScaleRegistry, default_scales
from ..telemetry import Telemetry
from ..terminology import MedicationCoder, build_coder
from ..transport import DestinationResolver, OsrmRouter, TransportService
from .contract import UIContract
from .media import dispose_incident_media
from .persistence import IncidentStore
from .encounters import SavedCall, encode_call, decode_call, fresh_relay
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
    fact_verifier: Optional[FactVerifier] = None   # keeps only what overheard words say about the patient
    fhir: Optional[FhirExport] = None
    fhir_document: Optional[FhirDocument] = None
    roster: Optional[PatientRoster] = None
    netem_mode: Optional[str] = None
    persistence: Optional[IncidentStore] = None
    extra: dict = field(default_factory=dict)
    capture_agent: object = None
    evidence_dir: Optional[Path] = None      # where agentic capture keeps redacted stills (deleted with the call)
    frame_reader: object = None
    speech_in_flight: int = 0
    previous_calls: list[SavedCall] = field(default_factory=list)
    transport: Optional[TransportService] = None   # destination list, vehicle position, road ETA
    dispositions: Optional[Dispositions] = None     # how an encounter can end (config/dispositions.yaml)

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
        if self.capture_agent is not None:
            self.capture_agent.set_auto(False)
        self.persist()
        return result

    def advance_incident(self, dispatch: Optional[str]) -> dict:
        # Bind the old queue before replacing the active roster. Each call keeps its own
        # authorization, destination, sequence numbers and retry packet.
        cleanup = self.end_incident()
        self.relay.get_incident = self.roster.incidents
        self.previous_calls.append(SavedCall(self.roster, self.relay))
        self.new_incident(dispatch)
        self.relay = fresh_relay(self, self.roster)
        self.persist()
        return cleanup

    def persist(self) -> None:
        if self.persistence:
            self.persistence.save({"v": 2, **encode_call(self.roster, self.relay),
                                   "previous_calls": [encode_call(c.roster, c.relay) for c in self.previous_calls]})

    def restore(self) -> bool:
        """Authenticate recovery before replacing state; retain completed calls and their outboxes."""
        payload = self.persistence.load() if self.persistence else None
        if not payload or payload.get("v") not in (1, 2) or not payload.get("patients"):
            return False
        active = decode_call(self, payload)
        self.previous_calls = [decode_call(self, row) for row in payload.get("previous_calls", [])]
        self.roster, self.relay = active.roster, active.relay
        return True

    def encounter_history(self) -> list[dict]:
        rows = []
        for call in reversed(self.previous_calls):
            pending_ids = {row[-1].id for row in call.relay.pending() + call.relay.withdrawals()}
            if call.relay.inflight:
                pending_ids.add(call.relay.inflight["i"])
            for inc, row in zip(call.roster.incidents(), call.roster.summaries()):
                full_pending = sum(f.status.value == "confirmed" for f in inc.facts) != call.relay.full_synced_facts.get(inc.id, 0)
                rows.append({**row, "started": inc.started.isoformat(),
                             "destination": (call.relay.authorized or {}).get("destination"),
                             "delivery_pending": inc.id in pending_ids or full_pending,
                             "authorized": bool(call.relay.authorized), "disposition": inc.disposition})
        return rows

    def derived_for_ed(self, inc) -> dict:
        """Values the ED gets that are not captured facts: the road-route arrival time while this unit transports,
        and, when the encounter ended without transport by this unit, that the patient is not coming."""
        out = {}
        if self.dispositions is not None and inc.disposition and not self.dispositions.transports(inc.disposition):
            out["encounter.disposition"] = self.dispositions.get(inc.disposition)["label"]
        elif self.transport is not None and inc.ended_at is None and not (inc.arrived_at or inc.transferred_at):
            arrive = self.transport.arrival(inc)
            if arrive is not None:
                out["transport.eta_at"] = arrive.replace(second=0, microsecond=0).isoformat()
        return out

    def receiver_for(self, destination: str) -> Optional[str]:
        """The receiving URL for a confirmed destination: that hospital's own, else the vehicle's default ED."""
        facility = self.transport.by_name(destination) if self.transport is not None else None
        return self.settings.ed_receivers.get(facility.id, self.settings.ed_url) if facility else self.settings.ed_url

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
        snap["encounter_history"] = self.encounter_history()
        snap["history_persisted"] = self.persistence is not None
        if self.transport is not None:
            crew = next((clock for clock in snap["clocks"] if clock["id"] == "eta"), None)
            snap["transport"] = self.transport.view(self.incident, crew)
            snap["clocks"] = [clock for clock in snap["clocks"] if clock["id"] != "eta"]
            eta = snap["transport"]["eta"]
            if eta and not (self.incident.arrived_at or self.incident.transferred_at):
                seconds = int((datetime.fromisoformat(eta["until"]) - utcnow()).total_seconds())
                snap["clocks"].append({"id": "eta", "label": "ETA", "until": eta["until"], "seconds": seconds,
                                       "source": eta["source"]})
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
                  embedder=None, protocol_fetch=None, normalizer: Optional[Normalizer] = None,
                  router: Optional[Router] = None) -> AppContext:
    s = settings or get_settings()
    vocab, scales, tiers, guard = default_vocabulary(), default_scales(), default_tiers(), default_guard()
    counties = CountyRegistry(s.county)
    checklists = ChecklistEngine.from_config(counties)
    trends = TrendRules.from_config()
    from ..config import load_yaml as _load_yaml
    from ..core.vital_severity import VitalRanges
    vital_ranges = VitalRanges.from_config(_load_yaml)
    corroboration = CorroborationRules.from_config()
    problems = corroboration.problems(vocab)
    if problems:
        raise ValueError("config/corroboration.yaml: " + "; ".join(problems))
    batch = BatchConfirmation(vocab, corroboration)
    fhir = FhirExport.from_config(vocab, scales)
    handoff = build_handoff(default_handoff_config(), vocab, scales, checklists, s)
    fhir_document = FhirDocument.from_config(fhir, handoff, s.unit_id)
    fhir_problems = fhir.problems() + fhir_document.problems()
    if fhir_problems:
        raise ValueError("config/fhir_codes.yaml: " + "; ".join(fhir_problems))
    projector = Projector(vocab, scales, checklists, counties, trends, ZoneInfo(s.timezone), s.reassess_min, batch,
                          vital_ranges)
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
        handoff=handoff, fhir=fhir, fhir_document=fhir_document,
        persistence=IncidentStore(s.state_dir, s.state_key_path) if s.persistence else None)
    ctx.new_incident(s.dispatch)
    ctx.dispositions = Dispositions(_load_yaml("dispositions.yaml"))
    ctx.transport = TransportService(lambda: counties.active, router or (OsrmRouter(s.routing_url) if s.routing_url else None),
                                     DestinationResolver(knowing))
    ctx.relay = Relay(lambda: ctx.roster.incidents(), s.ed_url, tiers=tiers, scales=scales, audio_dir=s.audio_dir,
                      egress=egress, ed_token=s.ed_token, derived=ctx.derived_for_ed)
    ctx.restored = ctx.restore()
    if text_model is None:                                  # real deployment: the local model checks overheard facts
        ctx.fact_verifier = FactVerifier(knowing)
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
                                lambda: counties.active["id"], picker=KeyPointPicker(knowing))
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
        if ctx.incident.ended_at or ctx.restored:
            from ..capture.types import CaptureResult
            return CaptureResult(reason="Encounter is not open for capture")
        return await service.photo(frame.jpeg, intent.mode, auto=True, frame=frame, intent=intent, roi=roi, valid=valid)

    agent = CaptureAgent(config, read, incident_id=lambda: ctx.incident.id,
                         speech_busy=lambda: ctx.speech_in_flight > 0, source=ctx.settings.capture_source,
                         notify=broadcast, hold=lambda id, reason: ctx.incident.hold_verification(id, reason))
    agent.set_auto(ctx.settings.capture_auto and ctx.settings.capture_source != "off"
                   and not ctx.restored and ctx.incident.ended_at is None)
    ctx.capture_agent = agent
    service.listeners.append(agent)
    source = None
    if ctx.settings.capture_source.startswith("replay:"):
        source = ReplayFrameSource(Path(ctx.settings.capture_source.partition(":")[2]), config["fps_in"], config)
    return service, source
