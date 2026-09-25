import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import type { FactView } from "@/lib/types";
import { factValue } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { captureAction } from "./actions";

export function MismatchCard({ fact }: { fact: FactView }) {
  const blocked = useHerald((s) => s.source === "fixture" || s.stale || s.conn !== "open");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const record = fact.value && typeof fact.value === "object" && !Array.isArray(fact.value) ? fact.value : {};
  const [drug, setDrug] = useState(String(record.drug ?? ""));
  async function resolve(action: "keep" | "edit") {
    if (busy || blocked) return;
    setBusy(true); setError("");
    try { await captureAction(`/api/capture/verify/${fact.id}`, { action, ...(action === "edit" ? { value: { ...record, drug: drug.trim() } } : {}) }); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not resolve this label check"); }
    finally { setBusy(false); }
  }
  const button = "min-h-12 rounded-xl border border-border-control bg-surface-1 px-4 py-2 text-button font-semibold";
  return <li className="mx-4 my-3 rounded-xl border border-medium-fg bg-medium-tint p-4" aria-label="Medication label mismatch">
    <h3 className="flex items-center gap-2 text-critical font-semibold"><TriangleAlert size={22} className="text-medium-fg" />CHECK · spoken drug and label differ</h3>
    <p className="mt-2 text-critical">Said <strong>{String(record.drug ?? "unknown")}</strong> · label: <strong>{fact.verify?.label_drug}</strong></p>
    <p className="mt-1 text-body">{factValue(fact)}</p>
    <p className="my-2 text-meta text-text-secondary">Held for your review. The image does not verify the dose, route, patient, or administration.</p>
    {fact.verify?.photo_id ? <a href={`/api/photo/${fact.verify.photo_id}`} target="_blank" rel="noreferrer" className="inline-block rounded-lg focus-visible:outline-2">
      <img src={`/api/photo/${fact.verify.photo_id}`} alt="Stored label evidence; open full image" className="mb-3 max-h-40 max-w-full rounded-lg" /></a>
      : <p className="mb-3 text-meta text-text-muted">Image not retained; visual evidence unavailable.</p>}
    {editing ? <form onSubmit={(e) => { e.preventDefault(); void resolve("edit"); }} className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-body">Correct recorded drug<input className="min-h-12 rounded-lg border border-border-control bg-surface-1 px-3" value={drug} onChange={(e) => setDrug(e.target.value)} required disabled={busy || blocked} /></label>
      <button className={button} type="submit" disabled={busy || blocked || !drug.trim()}>Save correction & confirm</button><button className={button} type="button" disabled={busy} onClick={() => setEditing(false)}>Cancel</button>
      <p className="w-full text-meta">Other dose details stay as recorded. The original event and its evidence remain in the audit history.</p>
    </form> : <div className="flex flex-wrap gap-3"><button className={button} disabled={busy || blocked} onClick={() => void resolve("keep")}>{busy ? "Saving…" : "Keep as said"}</button><button className={button} disabled={busy || blocked} onClick={() => setEditing(true)}>Edit</button></div>}
    {error && <p role="alert" className="mt-2 text-body">{error}</p>}
  </li>;
}
