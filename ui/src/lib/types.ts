// The contract between the Herald server and the screens. Derived from
// herald/core/snapshot.py (Projector.snapshot), herald/relay/relay.py status(), herald/api/trace.py,
// herald/api/capture.py and herald/api/context.py full_state(), checked against a live snapshot on 2026-09-24.
// When the backend changes a field, change it here in the same PR.

// ---------- enums (core/schema.py) ----------
export type Role = "medic" | "patient" | "family" | "bystander" | "device" | "photo" | "unknown";
export type CapturedBy = "medic" | "other" | "device" | "camera";
export type FactStatus = "unconfirmed" | "confirmed" | "rejected";
// Absolute clinical severity of a vital VALUE, from config/vital_ranges.yaml (backend-computed). Present only when a
// value is out of range, so its absence means "normal or not a graded vital" -- an older vehicle or a fixture simply
// omits it. It colours the value on the screen; it is never a diagnosis (AGENTS.md invariant 3). Distinct from
// `significant` on a trend, which means the value MOVED: a reading can be abnormal without moving, and moving without
// being abnormal.
export type VitalSeverity = "abnormal" | "critical";
/** A record is one event (a medication given, a procedure): only the fields said are present (config/vocabulary.yaml). */
export type FactRecord = Record<string, string | number | boolean>;
export type FactValue = string | number | boolean | string[] | FactRecord | null;
/** A code from a terminology (RxNorm, or ICD-10-CM for a class allergy); a list per item for list keys. */
export interface Coding { system: string; code: string }

// ---------- facts ----------
export interface Provenance {
  trigger?: string | null; frame_id?: string | null; auto?: boolean;
  observed_at?: string | null;
  audio_id: string | null; t_start: number | null; t_end: number | null; text: string | null;
  photo_id: string | null; crop: [number, number, number, number] | null; extractor: string | null;
  hold_reason: string | null;       // why this fact waits for the medic's tap
  normalized?: { said: string; coded: string; method: string }[];   // drug names as said → coded (§5.9d)
  // Room-microphone speech: whose information the check step read this as, from the words alone ("medic", "patient",
  // "husband"); `role` and `speaker` are set from it. Absent on older snapshots and on every other source.
  heard_as?: string | null;
}
export interface FactView {
  id: string; key: string; value: FactValue; unit: string | null; label: string;
  role: Role; speaker: string | null; captured_by: CapturedBy; confidence: number;
  provenance: Provenance; ts: string; status: FactStatus;
  previous_value: FactValue; previous_ts: string | null;
  severity?: VitalSeverity;
  code?: Coding | (Coding | null)[] | null;
  verify?: { status: "match" | "mismatch"; label_drug: string; photo_id: string | null; resolution: "kept" | "edited" | null } | null;
}

// ---------- checklists, gaps, trends ----------
export interface ReadinessItem { key: string; label: string; state: "done" | "pending" | "missing" }
export interface Readiness { id: string; label: string; done: number; total: number; ready: boolean; items: ReadinessItem[] }
export interface NeedItem { key: string; label: string; pending_confirm: boolean }
export interface Changed {
  key: string; label: string; series: number[]; times: string[]; delta: number;
  direction: "up" | "down" | "flat"; significant: boolean;
  // 2026-09-25: a trend point may now come from a camera read of the patient monitor that nobody has tapped yet.
  // `unconfirmed` is true when any point in `series` is still waiting; `unconfirmed_fact_ids` are those readings,
  // ready for POST /api/facts/confirm. `message` is the sentence to show (config/trends.yaml), present only when
  // the newest point is unconfirmed. Unconfirmed readings never reach the relay or the handoff report.
  // Optional: a recorded fixture or an older vehicle predates these fields, so a screen must read
  // their absence as "nothing is waiting" rather than crash or claim an unconfirmed reading.
  unconfirmed?: boolean; unconfirmed_fact_ids?: string[]; message?: string;
  // Absolute severity of the LATEST reading (config/vital_ranges.yaml), so a trend tile can colour a value that is
  // dangerous even when it did not move enough to be `significant`. Absent when the latest value is in range.
  severity?: VitalSeverity;
  // The smallest change worth noticing for this vital (config/trends.yaml abs_change / falls_by): a display hint the
  // sparkline uses as a minimum visible span, so a sub-threshold wobble does not render as dramatically as a cliff.
  floor?: number;
  // Per point in `series`: was that reading confirmed? A waiting camera/monitor point is drawn hollow, never as a value.
  confirmed?: boolean[];
  // Per point in `series` (2026-09-26): was it read off the patient monitor (the camera watching it, or a monitor
  // feed)? Monitor readings are recorded confirmed now, so this is how a screen says where the trend came from.
  from_monitor?: boolean[];
}

// ---------- scores (herald/scoring, config/scores/*.yaml) ----------
export type News2Band = "incomplete" | "not_applicable" | "low" | "low-medium" | "medium" | "high";
export interface News2 {
  name: string; score: number; complete: boolean; band: News2Band; any_single_3: boolean;
  parts: Record<string, { value: FactValue; points: number }>; missing: string[];
  thresholds: string; source: string; evidence: string;
  applicability: "applicable" | "unknown" | "excluded";
  applicability_reason: string | null; applicability_missing: string[];
}
export interface News2Point { ts: string; score: number; complete: boolean; band: News2Band }
/** An item-sum stroke scale: RACE, G.F.A.S.T. */
export interface StrokeScale {
  name: string; score: number; complete: boolean; positive: boolean | null;
  parts: Record<string, { value: number; points: number; max: number }>; missing: string[];
  thresholds: string; source: string; evidence: string;
}
export interface FieldTriage { name: string; red: string[]; yellow: string[]; missing: string[]; source: string }
export type StrokeScaleId = "RACE" | "GFAST";
/** A live, per-patient criteria score's own detail (trauma_605, field_triage, sepsis_700a04, stemi_700a08),
 * evaluated from confirmed facts only (herald/scoring/criteria.py). Not in `Scores` below because it is read
 * by score id, not by a fixed field name; see selectors.ts's criteriaScore(). */
export interface CriteriaRow {
  code: string | null; label: string; state: "met" | "not_met" | "unknown"; group?: string;
  finding?: string; needs?: string[]; parts?: CriteriaRow[];
}
export interface CriteriaScoreDetail {
  name: string; county: string | null; applies: boolean; met: boolean; level: string | null;
  complete: boolean; missing: string[]; criteria: CriteriaRow[]; source: string; thresholds: string | null;
}
export interface Scores {
  news2: News2; news2_history: News2Point[]; race: StrokeScale; gfast: StrokeScale; field_triage: FieldTriage;
  stroke_scales: StrokeScaleId[];          // the county's scales, primary first
  primary_stroke_scale: StrokeScaleId;
}

// ---------- alerts ----------
export type Alert =
  | { type: "trauma_alert_criteria"; label: string; level: string; score: string; criteria: string[]; county_rule?: string[]; county?: string }
  | { type: "sepsis_prenotification"; label: string; level: string; score: string; criteria: string[]; county_rule?: string[]; county?: string }
  | { type: "contradiction"; key: string; label: string; confirm_fact_id: string; facts: FactView[] }
  | { type: "confirm_required"; key: string; label: string; confirm_fact_id: string; facts: FactView[] }
  | { type: "significant_change"; key: string; label: string; series: number[];
      // 2026-09-25: same labelling as Changed. Render `message` when present and offer the tap; never imply the
      // value has been sent to the ED.
      unconfirmed?: boolean; unconfirmed_fact_ids?: string[]; message?: string }
  | { type: "news2_rise"; label: string; from: number; to: number; band: News2Band }
  | { type: "news2_high"; label: string; score: number; band: "high" }
  | { type: "race_positive"; label: string; score: number }
  | { type: "gfast_positive"; label: string; score: number; county_rule: string; county: string }
  | { type: "stemi_alert"; score: "stemi_700a08"; label: string; level: "trigger"; criteria: string[];
      county_rule?: string[]; county?: string };
export type AlertType = Alert["type"];

// ---------- clocks ----------
export interface Clock {
  id: "scene" | "lkw" | "eta" | "reassess"; label: string; seconds: number;
  since?: string; until?: string; confirmed?: boolean;
  source?: "route" | "crew";            // eta only: road route from the vehicle's position, or the crew's estimate
}

// ---------- destination and ETA (herald/transport/service.py `view`) ----------
export interface TransportOption { id: string; name: string; designations: string[]; point: string | null; minutes: number | null; km: number | null }
export interface TransportView {
  routing: boolean; router_error: string | null;
  position: { at: string; accuracy_m: number | null; fresh: boolean } | null;
  options: TransportOption[];            // the county's receiving hospitals, nearest first when the position is fresh
  /** The confirmed destination and how it was set: from the crew's words, Herald's suggestion accepted, or chosen. */
  destination: { fact_id: string; value: string; id: string | null; how: "heard" | "suggested" | "chosen"; said: string | null; at: string } | null;
  /** Destination words that are not the destination: still matching, naming no single county hospital, or another
   *  speaker's (then `id` is the hospital they named, offered as the suggestion). */
  heard: { fact_id: string; value: string; role: string; state: "matching" | "matched" | "unmatched"; id: string | null } | null;
  suggestion: TransportSuggestion | null;
  eta: { source: "route" | "crew"; until: string } | null;
}
/** The ONE hospital Herald suggests (herald/transport/selection.py): the county's rule for this situation, or the
 *  hospital another speaker named. Accepted with a tap or by saying the hospital. */
export interface TransportSuggestion {
  id: string; name: string; designations: string[]; minutes: number | null; km: number | null; nearest_known: boolean;
  basis: "policy" | "heard"; rule: string | null; situation: string; service: string | null; cite: string | null;
  quote: string | null; note: string | null;
}

// ---------- trace (api/trace.py, api/capture.py) ----------
export interface TraceFact {
  id: string; key: string; label: string; value: FactValue; role: Role; speaker: string | null;
  status: FactStatus; confidence: number; extractor: string | null; relay: string; hold_reason: string | null;
  code?: Coding | (Coding | null)[] | null;
}
export interface SttInfo { seconds: number | null; chunks: { text: string; t: [number | null, number | null] }[]; ms?: number; error?: string; language?: string | null }
export interface RejectedFact { key: string; value: FactValue; reason: string }
export interface Trace {
  heard: { text: string; speaker?: string | null; audio_id?: string | null; photo_id?: string | null; frame_id?: string;
           stt?: SttInfo | null; source?: "structured" };
  rules: { ms: number; facts: TraceFact[]; rejected?: RejectedFact[] };
  model: {
    // "unavailable": the extraction model isn't served, nothing was extracted, the words are kept (the POST got 503)
    status: "running" | "done" | "error" | "off" | "skipped" | "unavailable"; name?: string | null; ms?: number;
    tokens?: number | null; proposed?: number; auto_confirm_threshold?: number;
    facts?: TraceFact[]; error?: string; reason?: string; retry?: boolean; rejected?: RejectedFact[];
  };
  guard?: { instruction_shaped: string | null; policy?: string };
  effects: {
    readiness: { label: string; from: number; to: number; total: number; ready: boolean }[];
    alerts_new: { type: AlertType; label: string }[];
    scores: { name: string; from: number | null; to: number; detail: string | boolean }[];
    gaps_closed: string[];
  };
}
export interface TranscriptEntry {
  trigger?: string; reason?: string; frame_id?: string;
  id: string; ts: string; text: string; captured_by: CapturedBy; speaker: string | null;
  audio_id: string | null; photo_id?: string; fact_ids: string[];
  extract: { rules: number; llm: number | null; ms: number };
  stt?: SttInfo | null; trace: Trace;
}

// ---------- mass-casualty patient roster (TASK_SPECS S5) ----------
export type TriageCategory = "immediate" | "delayed" | "minimal" | "expectant" | "dead";
export interface PatientSummary {
  ended_at?: string | null;
  id: string; label: string; slot?: string; triage: TriageCategory | null; summary: string;
  readiness_done: number; readiness_total: number;
}

// ---------- relay (relay/relay.py status()) ----------
export type LinkState = "good" | "weak" | "down" | "unknown" | "not configured";
export interface RelayLogEntry {
  patient?: string;
  ts: string; seq: number; tier: "critical" | "full"; bytes: number; keys: string[]; why: string[];
  removed: string[]; queued_after: number; result: "acked" | "failed"; rtt_ms?: number; error?: string;
}
export interface RelayStatus {
  patients?: Record<string, { triage: string | null; pending: number; sync: Record<string, "sent" | "queued"> }>;
  configured: boolean; ed_url: string | null;
  authorized: { destination: string; scope: string; at: string } | null;
  link: LinkState; pending: { patient?: string; key: string; priority: number; why: string }[];
  sync: Record<string, "sent" | "queued">; bytes_sent: number; local_bytes: number;
  kept_local_pct: number; packets_acked: number; retries: number; duplicates_acked?: number; last_ack_at: string | null;
  clinician_acknowledgements?: Record<string, { at: string; status: "received" | "cath_lab_activated"; note?: string | null }[]>;
  log: RelayLogEntry[];
  /** The final report sent at hand over: null before it; delivered_at when the ED's system acknowledged it,
   *  received_at when a person at the ED marked it received. Absent on older vehicles and recorded fixtures. */
  handover?: HandoverDelivery | null;
}
export interface HandoverDelivery { at: string; delivered_at: string | null; received_at: string | null }

// ---------- protocol lookup ----------
export interface ProtocolStatus {
  ready: boolean; county: string; sections: number; missing: string[]; review_required: string[];
  last_sync: string | null; destination_audit_ok: boolean;
  documents: { id: string; title: string; effective: string }[];
}
export interface ProtocolPassage {
  doc: string; title: string | null; section: string; heading: string; page: number;
  text: string;                          // heading + body as printed, shown verbatim
  parents: string[]; score: number; effective: string | null; text_layer_uncertain: boolean;
}
export interface ProtocolAnswer {
  query: string;
  answerable: boolean | null;            // null: no reranker ran (or it failed)
  reranked: boolean; chosen?: number; error?: string;
  results: ProtocolPassage[];
}

/** herald/knowledge/cues.py: the county's own passage for a recognised situation, verbatim with its citation. */
export interface ProtocolCue {
  id: string; title: string; query: string; asked?: boolean; found_at?: string;
  points?: { text: string; items?: string[]; cite: string; marks: string[] }[];   // the model's picks among the county's own rules; a lead-in keeps its list
  state: "searching" | "found" | "not_covered";
  passages: { doc: string; title: string | null; section: string; heading: string | null; page: number | null;
    effective: string | null; text: string; shortened: boolean; text_layer_uncertain: boolean }[];
}

// ---------- the snapshot (api/context.py full_state()) ----------
export interface Snapshot {
  capture?: CaptureStatus;
  capture_groups?: CaptureGroup[];      // absent on older vehicles and recorded fixtures
  incident: {
    id: string; dispatch: string | null; started: string; ended_at: string | null;
    arrived_at?: string | null; transferred_at?: string | null;
    disposition?: string | null;         // config/dispositions.yaml id, set when the encounter is finished
    // 2026-09-26: the one "hand over" step (POST /api/encounters/current/handover) sets handed_over_at together with
    // transferred_at and ended_at. `not_obtained` lists the required items the medic marked "unable to obtain"
    // (POST /api/handoff/not-obtained). Optional: older vehicles and recorded fixtures predate both.
    handed_over_at?: string | null; handed_over_to?: string | null; not_obtained?: string[];
    media_disposal: MediaDisposal | null;
  };
  patients: PatientSummary[];
  encounter_history?: (PatientSummary & { started: string; destination: string | null; authorized: boolean; delivery_pending: boolean; disposition?: string | null })[];
  history_persisted?: boolean;
  active_patient: string;
  restored: boolean;                     // unfinished call recovered after a server restart
  summary: string;
  readiness: Readiness[];
  needs_attention: { missing: NeedItem[]; unknown: NeedItem[] };
  changed: Changed[];
  scores: Scores;
  county: { id: string; name: string };
  alerts: Alert[];
  clocks: Clock[];
  facts: Record<string, FactView>;       // latest non-rejected fact per key
  events?: Record<string, FactView[]>;   // event keys (meds.given, procedures.done): every event, in order
  timeline: FactView[];                  // last 60 facts, all statuses
  audit: { at: string; action: "fact_status_changed"; actor: string; fact_id: string; key: string;
           from: FactStatus; to: FactStatus }[];
  transcripts: TranscriptEntry[];        // last 20
  ed_sync: Record<string, "sent" | "queued">;
  counters: { facts: number; cloud_ai_calls: number };
  relay: RelayStatus;
  netem: "good" | "weak" | "down" | null;
  protocols?: ProtocolStatus;            // absent when protocol lookup is off
  transport?: TransportView;             // absent on older vehicles and older recordings
  protocol_cues?: ProtocolCue[];         // the county passage for each situation Herald recognises (config/protocol_cues.yaml)
}

/** One camera frame's still-unconfirmed readings (herald/core/corroboration.py, docs/API_CONTRACT.md). */
export interface CaptureGroup {
  frame_id: string; trigger: string | null; photo_id: string | null; ts: string;
  batch_fact_ids: string[];              // one POST /api/readings/{frame_id}/confirm confirms all of these
  individual: { id: string; key: string; label: string; reason: string | null }[];
}

export interface CaptureStatus {
  auto: boolean; source: string; fps_in: number; incident_id: string; sees: "off" | "watching" | "reading";
  roi: { x0: number; y0: number; x1: number; y1: number } | null;
  last: { ts: number; trigger: string; mode: string; reason: string; facts: string[]; photo_id: string | null } | null;
  counts: { frames: number; gated: number; captured: number; stored: number };
  error: string | null; pending: number;
}

export interface MediaDisposal {
  at: string;
  deleted: { audio: string[]; photo: string[] };
  missing: { audio: string[]; photo: string[] };
  invalid: { audio: string[]; photo: string[] };
  patients?: Record<string, Omit<MediaDisposal, "patients">>;
}
export type NowMessage = { type: "state"; state: Snapshot } | { type: "pong"; t: string };

// ---------- REST ----------
/** GET /api/handoff (herald/reporting/handoff.py), also the reply to POST /api/handoff/not-obtained. */
export type HandoffLineStatus = "confirmed" | "missing" | "not_obtained" | "empty";
export interface HandoffItem { key: string; label: string }
/** One confirmed fact behind a report line: who gave it and when (herald/reporting/view.py). */
export interface HandoffSource {
  fact_id: string; key: string; role: Role | string; speaker: string | null;
  captured_by?: CapturedBy | string; time?: string | null; ts?: string | null;
  audio_id?: string | null; photo_id?: string | null; extractor?: string | null;
  observed_at?: string | null; frame_id?: string | null;
}
export interface HandoffLine {
  text: string; status: HandoffLineStatus | string;
  // optional: a recorded fixture's summary and older servers send the text and status only
  kind?: string; keys?: string[]; fact_ids?: string[]; sources?: HandoffSource[];
}
export interface HandoffSection { id: string; label: string; say_label?: boolean; source?: string; lines: HandoffLine[] }
/** Who told us what (herald/reporting/informants.py): `items` are the labels of what they told, in reading order. */
export interface HandoffInformant { who: string; role: Role | string; keys: string[]; items: string[] }
export interface HandoffReportData {
  incident: { id: string }; as_of: string; text: string;
  format: { id: string; label: string; title: string }; formats: { id: string; label: string }[];
  sections: HandoffSection[];
  not_yet_known: HandoffItem[]; not_yet_confirmed: HandoffItem[];
  not_obtained?: HandoffItem[];          // optional: a server from before 2026-09-26 does not send it
  informants?: HandoffInformant[];       // optional: a server (or recording) from before 2026-09-26 does not send it
}

/** GET /api/telemetry (herald/telemetry/collector.py): every field may be missing or null (no GPU reading yet, the
 *  model server's metrics unreachable, an older server). */
export type TelemetryKind = "stt" | "text" | "vision";
export interface TelemetryRequest { kind: TelemetryKind | string; duration_s: number | null; energy_j: number | null; energy_wh?: number | null; watts_avg?: number | null }
export interface Telemetry {
  since_s?: number | null; power_w_now?: number | null; power_w_avg_60s?: number | null; gpu_util_pct?: number | null;
  energy_wh?: number | null;
  requests?: { attributed_energy_wh?: number | null; count?: number | null; recent?: TelemetryRequest[] | null } | null;
  tokens?: { prompt?: number | null; completion?: number | null } | null;
  calls?: { llm?: number | null; vision?: number | null; stt?: number | null } | null;
  stt_audio_min?: number | null;
  cost?: { local_usd?: number | null; cloud_equivalent_usd?: number | null; net_savings_usd?: number | null;
    cloud_breakdown?: { llm_usd?: number | null; stt_usd?: number | null } | null } | null;
  cloud_ai_calls?: number | null;
  model_server?: { mean_request_latency_s?: number | null; generation_tok_s_last_30s?: number | null; running?: number | null } | null;
  assumptions?: {
    electricity_usd_per_kwh?: number | null; cloud_llm_usd_per_1m_in?: number | null; cloud_llm_usd_per_1m_out?: number | null;
    cloud_stt_usd_per_min?: number | null; sources?: Record<string, string> | null; energy_scope?: string | null;
  } | null;
}

export interface Health {
  // *_available: the model server is actually serving that label now; llm_model names it even when it isn't
  llm_model: string | null; llm_available?: boolean; vision_model?: string | null; vision_available?: boolean;
  stt_model: string; stt_loaded: boolean; incident: string; county?: string; cloud_ai_calls: number;
  terminology?: { rxnorm_release: string };
}

// ---------- fixtures (scripts/record_ws.py) ----------
export interface FixtureLine { t_ms: number; msg: NowMessage }
