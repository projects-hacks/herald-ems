// The contract between the Herald server and the screens (docs/UX_PLAN.md §5.6). Derived from
// herald/core/snapshot.py (Projector.snapshot), herald/relay/relay.py status(), herald/api/trace.py,
// herald/api/capture.py and herald/api/context.py full_state(), checked against a live snapshot on 2026-09-24.
// When the backend changes a field, change it here in the same PR.

// ---------- enums (core/schema.py) ----------
export type Role = "medic" | "patient" | "family" | "bystander" | "device" | "photo";
export type CapturedBy = "medic" | "other" | "device" | "camera";
export type FactStatus = "unconfirmed" | "confirmed" | "rejected";
/** A record is one event (a medication given, a procedure): only the fields said are present (config/vocabulary.yaml). */
export type FactRecord = Record<string, string | number | boolean>;
export type FactValue = string | number | boolean | string[] | FactRecord | null;
/** A code from a terminology (RxNorm, or ICD-10-CM for a class allergy); a list per item for list keys (UX_PLAN §5.9d). */
export interface Coding { system: string; code: string }

// ---------- facts ----------
export interface Provenance {
  trigger?: string | null; frame_id?: string | null; auto?: boolean;
  audio_id: string | null; t_start: number | null; t_end: number | null; text: string | null;
  photo_id: string | null; crop: [number, number, number, number] | null; extractor: string | null;
  hold_reason: string | null;       // why this fact waits for the medic's tap (UX_PLAN §5.9a)
  normalized?: { said: string; coded: string; method: string }[];   // drug names as said → coded (§5.9d)
}
export interface FactView {
  id: string; key: string; value: FactValue; unit: string | null; label: string;
  role: Role; speaker: string | null; captured_by: CapturedBy; confidence: number;
  provenance: Provenance; ts: string; status: FactStatus;
  previous_value: FactValue; previous_ts: string | null;
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
}

// ---------- scores (herald/scoring, config/scores/*.yaml) ----------
export type News2Band = "incomplete" | "low" | "low-medium" | "medium" | "high";
export interface News2 {
  name: string; score: number; complete: boolean; band: News2Band; any_single_3: boolean;
  parts: Record<string, { value: FactValue; points: number }>; missing: string[];
  thresholds: string; source: string; evidence: string;
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
export interface Scores {
  news2: News2; news2_history: News2Point[]; race: StrokeScale; gfast: StrokeScale; field_triage: FieldTriage;
  stroke_scales: StrokeScaleId[];          // the county's scales, primary first
  primary_stroke_scale: StrokeScaleId;
}

// ---------- alerts ----------
export type Alert =
  | { type: "trauma_alert_criteria" | "sepsis_prenotification"; label: string; level: string; score: string; criteria: string[]; county_rule?: string[]; county?: string }
  | { type: "contradiction"; key: string; label: string; confirm_fact_id: string; facts: FactView[] }
  | { type: "confirm_required"; key: string; label: string; confirm_fact_id: string; facts: FactView[] }
  | { type: "significant_change"; key: string; label: string; series: number[] }
  | { type: "news2_rise"; label: string; from: number; to: number; band: News2Band }
  | { type: "race_positive"; label: string; score: number }
  | { type: "gfast_positive"; label: string; score: number; county_rule: string; county: string };
export type AlertType = Alert["type"];

// ---------- clocks ----------
export interface Clock {
  id: "scene" | "lkw" | "eta" | "reassess"; label: string; seconds: number;
  since?: string; until?: string; confirmed?: boolean;
}

// ---------- trace (api/trace.py, api/capture.py) ----------
export interface TraceFact {
  id: string; key: string; label: string; value: FactValue; role: Role; speaker: string | null;
  status: FactStatus; confidence: number; extractor: string | null; relay: string; hold_reason: string | null;
  code?: Coding | (Coding | null)[] | null;
}
export interface SttInfo { seconds: number; chunks: { text: string; t: [number | null, number | null] }[]; ms?: number }
export interface RejectedFact { key: string; value: FactValue; reason: string }
export interface Trace {
  heard: { text: string; speaker?: string | null; audio_id?: string | null; photo_id?: string | null; frame_id?: string;
           stt?: SttInfo | null; source?: "structured" };
  rules: { ms: number; facts: TraceFact[]; rejected?: RejectedFact[] };
  model: {
    // "unavailable": the extraction model isn't served, nothing was extracted, the words are kept (the POST got 503)
    status: "running" | "done" | "error" | "off" | "skipped" | "unavailable"; name?: string | null; ms?: number;
    tokens?: number | null; proposed?: number; auto_confirm_threshold?: number;
    facts?: TraceFact[]; error?: string; reason?: string; rejected?: RejectedFact[];
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
  id: string; label: string; triage: TriageCategory | null; summary: string;
  readiness_done: number; readiness_total: number;
}

// ---------- relay (relay/relay.py status()) ----------
export type LinkState = "good" | "weak" | "down" | "unknown" | "not configured";
export interface RelayLogEntry {
  patient?: string;
  ts: string; seq: number; tier: "critical" | "full"; bytes: number; keys: string[]; why: string[];
  queued_after: number; result: "acked" | "failed"; rtt_ms?: number; error?: string;
}
export interface RelayStatus {
  patients?: Record<string, { triage: string | null; pending: number; sync: Record<string, "sent" | "queued"> }>;
  configured: boolean; ed_url: string | null;
  authorized: { destination: string; scope: string; at: string } | null;
  link: LinkState; pending: { patient?: string; key: string; priority: number; why: string }[];
  sync: Record<string, "sent" | "queued">; bytes_sent: number; local_bytes: number;
  kept_local_pct: number; packets_acked: number; retries: number; last_ack_at: string | null;
  log: RelayLogEntry[];
}

// ---------- protocol lookup (UX_PLAN §5.9b) ----------
export interface ProtocolStatus {
  ready: boolean; county: string; sections: number; missing: string[]; review_required: string[];
  last_sync: string | null; destination_audit_ok: boolean;
  documents: { id: string; title: string; effective: string }[];
}

// ---------- the snapshot (api/context.py full_state()) ----------
export interface Snapshot {
  capture?: CaptureStatus;
  incident: { id: string; dispatch: string | null; started: string };
  patients: PatientSummary[];
  active_patient: string;
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
  transcripts: TranscriptEntry[];        // last 20
  ed_sync: Record<string, "sent" | "queued">;
  counters: { facts: number; cloud_ai_calls: number };
  relay: RelayStatus;
  netem: "good" | "weak" | "down" | null;
  protocols?: ProtocolStatus;            // absent when protocol lookup is off
}

export interface CaptureStatus {
  auto: boolean; source: string; fps_in: number; incident_id: string; sees: "off" | "watching" | "reading";
  roi: { x0: number; y0: number; x1: number; y1: number } | null;
  last: { ts: number; trigger: string; mode: string; reason: string; facts: string[]; photo_id: string | null } | null;
  counts: { frames: number; gated: number; captured: number; stored: number };
  error: string | null; pending: number;
}
export type NowMessage = { type: "state"; state: Snapshot } | { type: "pong"; t: string };

// ---------- REST ----------
export interface Health {
  // *_available: the model server is actually serving that label now; llm_model names it even when it isn't
  llm_model: string | null; llm_available?: boolean; vision_model?: string | null; vision_available?: boolean;
  stt_model: string; stt_loaded: boolean; incident: string; county?: string; cloud_ai_calls: number;
  terminology?: { rxnorm_release: string };
}

// ---------- fixtures (scripts/record_ws.py) ----------
export interface FixtureLine { t_ms: number; msg: NowMessage }
