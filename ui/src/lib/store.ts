// The one client store (docs/API_CONTRACT.md). The server's snapshot is replaced on every message; UI state (expanded cards,
// seen alerts, theme) lives beside it, so a card keeps its state when the server updates it.
import { create } from "zustand";
import { alertKey } from "./selectors";
import type { Health, Snapshot } from "./types";

export type Theme = "dark" | "light";
export type TypeScale = 1 | 1.25 | 1.5;
export type IncidentPhase = "scene" | "transport" | "handoff";
export type Pending = "pending" | "sent" | { error: string };
export type Page = "overview" | "patient" | "trends" | "handoff" | "transcript" | "review" | "camera" | "patients" | "settings" | "protocols";
export const PAGES: Page[] = ["overview", "patient", "trends", "handoff", "transcript", "review", "camera", "patients", "settings", "protocols"];

export interface UiState {
  theme: Theme; typeScale: TypeScale;
  reducedMotion: boolean; keyboardPtt: boolean;
  expanded: Record<string, boolean>;
  seenAlerts: Record<string, true>;
  /** Push-to-talk is held (U4 sets it): alerts that arrive meanwhile wait until release (§3.1.8, P4). */
  heldAlerts: boolean;
  page: Page;
  confirmNewIncident: boolean; confirmEndIncident: boolean;
  incidentPhase: IncidentPhase;
}

export interface FixtureState { name: string; index: number; total: number; playing: boolean; speed: number }

export interface HeraldState {
  snapshot: Snapshot | null;
  conn: "connecting" | "open" | "closed";
  connectingSince: number;          // performance.now() when the current (re)connect attempt series began
  lastMessageAt: number;            // performance.now() of the last state or pong
  lastStateAt: number;              // Date.now() of the last state (shown as "last update hh:mm:ss")
  stale: boolean;
  source: "live" | "fixture";
  fixture: FixtureState | null;
  health: Health | null;
  ui: UiState;
  pending: Record<string, Pending>;
  /** When each alert first appeared on this screen (an increasing counter): the server lists alerts by type,
   *  not by time, so arrival order is tracked here for "newest first" (docs/API_CONTRACT.md). */
  alertArrival: Record<string, number>;
  /** The arrival counter when push-to-talk was pressed; alerts that arrived later are held back. null = not held. */
  holdMark: number | null;
  toast: { text: string; at: number } | null;
  setSnapshot: (s: Snapshot) => void;
  setUi: (patch: Partial<UiState>) => void;
  toggleExpanded: (id: string) => void;
  markSeen: (...alertKeys: string[]) => void;
  holdAlerts: (on: boolean) => void;
  showToast: (text: string) => void;
}

// ---------- per-device preferences (localStorage can throw or be empty: never rely on it) ----------
const PREFS = "herald.ui.v1";
type Prefs = Pick<UiState, "theme" | "typeScale" | "reducedMotion" | "keyboardPtt">;
const PREF_KEYS: (keyof Prefs)[] = ["theme", "typeScale", "reducedMotion", "keyboardPtt"];

function readPrefs(): Partial<Prefs> {
  try {
    return JSON.parse(localStorage.getItem(PREFS) ?? "{}") as Partial<Prefs>;
  } catch {
    return {};
  }
}
function writePrefs(p: Prefs) {
  try {
    localStorage.setItem(PREFS, JSON.stringify(p));
  } catch {
    /* private window or blocked storage: preferences just aren't remembered */
  }
}

/** URL parameters select the page and override appearance preferences. Old explain links open the capture timeline. */
export function initialUi(search = typeof location === "undefined" ? "" : location.search): UiState {
  const q = new URLSearchParams(search);
  const p = readPrefs();
  const t = Number(q.get("type"));
  const page = q.get("page") as Page | null;
  return {
    theme: q.get("theme") === "light" ? "light" : q.get("theme") === "dark" ? "dark" : (p.theme ?? "dark"),
    typeScale: t === 1.25 || t === 1.5 ? t : (p.typeScale ?? 1),
    reducedMotion: p.reducedMotion ?? false,
    keyboardPtt: p.keyboardPtt ?? true,
    expanded: {},
    seenAlerts: {},
    heldAlerts: false,
    page: page && PAGES.includes(page) ? page : q.get("mode") === "explain" ? "transcript" : "overview",
    confirmNewIncident: false,
    incidentPhase: "scene",
    confirmEndIncident: false,
  };
}

export const useHerald = create<HeraldState>()((set, get) => ({
  snapshot: null,
  conn: "connecting",
  connectingSince: 0,
  lastMessageAt: 0,
  lastStateAt: 0,
  stale: false,
  source: "live",
  fixture: null,
  health: null,
  ui: initialUi(),
  pending: {},
  alertArrival: {},
  holdMark: null,
  toast: null,
  setSnapshot: (s) => {
    const switched = get().snapshot !== null && get().snapshot?.incident.id !== s.incident.id;
    // An action whose request succeeded stays pending until the next snapshot: no optimistic updates (§5.7).
    const pending = Object.fromEntries(Object.entries(get().pending).filter(([, v]) => v !== "sent"));
    const arrival = switched ? {} : { ...get().alertArrival };
    let next = Object.keys(arrival).length;
    for (const a of s.alerts) {
      const k = alertKey(a);
      if (!(k in arrival)) arrival[k] = ++next;
    }
    set({ snapshot: s, pending: switched ? {} : pending, alertArrival: arrival, lastStateAt: Date.now(),
      ...(switched ? { ui: { ...get().ui, page: "overview", incidentPhase: "scene", seenAlerts: {}, expanded: {}, heldAlerts: false }, holdMark: null } : {}) });
  },
  setUi: (patch) => {
    const ui = { ...get().ui, ...patch };
    set({ ui });
    if (PREF_KEYS.some((k) => k in patch)) {
      writePrefs({ theme: ui.theme, typeScale: ui.typeScale, reducedMotion: ui.reducedMotion, keyboardPtt: ui.keyboardPtt });
    }
  },
  toggleExpanded: (id) => {
    const ui = get().ui;
    set({ ui: { ...ui, expanded: { ...ui.expanded, [id]: !ui.expanded[id] } } });
  },
  markSeen: (...keys) => {
    const ui = get().ui;
    set({ ui: { ...ui, seenAlerts: { ...ui.seenAlerts, ...Object.fromEntries(keys.map((k) => [k, true as const])) } } });
  },
  holdAlerts: (on) => set({ ui: { ...get().ui, heldAlerts: on }, holdMark: on ? Object.keys(get().alertArrival).length : null }),
  showToast: (text) => set({ toast: { text, at: Date.now() } }),
}));
