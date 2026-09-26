// Labels, units, relay tiers and change rules: the UI contract (GET /api/meta, exported to public/contract/ so a
// fixture replay needs no server). Loaded once at start-up.
import { useEffect, useState } from "react";

/** A score contract row's static criterion: code/label always; `tap` only when a medic's own tap can record it
 * through the existing POST /api/facts (a plain `contains` rule over an accumulating list key) — see
 * herald/api/contract.py's `_tap`. No `tap` means read-only here (vitals, medications, computed values). */
export interface ContractCriterion { group: string; code: string | null; label: string; parent: string | null; tap?: { key: string; value: string } }
export interface ContractScore {
  name: string; kind: string; county: string | null; source: string; thresholds?: string; relay_key: string;
  groups?: { id: string; label: string; short?: string; met?: boolean; priority?: string }[];
  criteria?: ContractCriterion[];
}
export interface Contract {
  keys: Record<string, { label: string; type: string; kind?: string; unit?: string; range?: [number, number] }>;
  relayTiers: Record<string, { tier: number; why: string }>;
  changeRules: Record<string, string>;
  checklists?: Record<string, { label?: string }>;
  scores?: Record<string, ContractScore>;
  dispositions?: Disposition[];                 // how an encounter can end (config/dispositions.yaml)
  derivedLabels?: Record<string, string>;       // relay keys that are not captured facts (route ETA, outcome)
}
export interface Disposition { id: string; label: string; detail?: string; transport: boolean }
let cache: Contract | null = null;
let loading: Promise<Contract> | null = null;

export function loadContract(): Promise<Contract> {
  if (cache) return Promise.resolve(cache);
  loading ??= (async (): Promise<Contract> => {
    if (!new URLSearchParams(location.search).has("fixture")) {
      try {
        const response = await fetch("/api/meta", { signal: AbortSignal.timeout(3000) });
        if (response.ok) {
          const meta = await response.json();
          if (meta.keys && meta.relay_tiers) return (cache = { keys: meta.keys, relayTiers: meta.relay_tiers, changeRules: meta.change_rules ?? {}, checklists: meta.checklists, scores: meta.scores,
            dispositions: meta.dispositions, derivedLabels: meta.derived_labels });
        }
      } catch { /* Offline fixture labels remain available. */ }
    }
    return Promise.all(["keys", "relay_tiers", "change_rules", "checklists", "scores", "dispositions", "derived_labels"].map((f) =>
    fetch(`/contract/${f}.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}))))
    .then(([keys, relayTiers, changeRules, checklists, scores, dispositions, derivedLabels]): Contract => {
      const result: Contract = { keys, relayTiers, changeRules, checklists, scores,
        dispositions: Array.isArray(dispositions) ? dispositions : undefined, derivedLabels }; cache = result; return result;
    });
  })();
  return loading;
}
export function useContract(): Contract | null {
  const [c, setC] = useState<Contract | null>(cache);
  useEffect(() => { if (!c) loadContract().then(setC); }, [c]);
  return c;
}
export function label(c: Contract | null, key: string): string {
  if (key === "alert.readiness") return "Pre-alert";
  if (c?.derivedLabels?.[key]) return c.derivedLabels[key];
  if (key.startsWith("score.")) return { news2: "NEWS2", race: "RACE", gfast: "G.F.A.S.T." }[key.slice(6)] ?? key;
  return c?.keys[key]?.label ?? key;
}
