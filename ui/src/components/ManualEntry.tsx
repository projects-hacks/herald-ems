import { useState } from "react";
import { ClipboardPen } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./ui/dialog";
import { Button } from "./kit";
import { act } from "@/lib/api";
import { useContract } from "@/lib/contract";
import { manualValue } from "@/lib/manual";
import { useHerald } from "@/lib/store";

/** `field` opens the form on one field (the handoff's "Add" for a missing item); `trigger` and `triggerLabel` replace the
 *  default "Manual entry" button's text and accessible name. */
export function ManualEntry({ field, trigger, triggerLabel }: { field?: string; trigger?: string; triggerLabel?: string } = {}) {
  const contract = useContract();
  const disabled = useHerald((s) => s.source === "fixture" || s.stale || s.conn !== "open" || s.ui.heldAlerts || !!s.snapshot?.incident.ended_at || !!s.snapshot?.incident.handed_over_at || !!s.snapshot?.restored);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(field ?? "");
  const [raw, setRaw] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const meta = contract?.keys[key];
  const control = "min-h-12 rounded-xl border border-border-control bg-surface-2 px-3 text-body text-text-primary";
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!meta || disabled || busy) return;
    try {
      const value = manualValue(raw, meta);
      setError(""); setBusy(true);
      const saved = await act("manual-entry", "/api/facts", [{ key, value, unit: meta.unit ?? null,
        captured_by: "medic", role: "medic", speaker: "manual entry", confidence: 1,
        provenance: { extractor: "manual", text: `${meta.label}: ${raw}` } }]);
      if (saved) { setRaw(""); setOpen(false); }
      else setError("Entry could not be verified as saved. Review the patient record before trying again.");
    } catch (e) { setError(e instanceof Error ? e.message : "Check this value."); }
    finally { setBusy(false); }
  };
  return <>
    <Button size="lg" disabled={disabled} aria-label={triggerLabel} onClick={() => { if (field) setKey(field); setOpen(true); }}><ClipboardPen size={18} />{trigger ?? "Manual entry"}</Button>
    <Dialog open={open} onOpenChange={(value) => { if (!busy) setOpen(value); }}>
      <DialogContent>
        <DialogTitle>Enter a patient fact</DialogTitle>
        <DialogDescription>Works without speech recognition or a language model. Your entry is attributed to you. Conflicting values and code status still require review.</DialogDescription>
        <form onSubmit={save} className="flex flex-col gap-4">
          <label className="flex flex-col gap-2 text-body font-medium">Field
            <select required value={key} onChange={(e) => { setKey(e.target.value); setRaw(""); setError(""); }} className={control}>
              <option value="">Choose a field</option>
              {Object.entries(contract?.keys ?? {}).map(([id, item]) => <option key={id} value={id}>{item.label}{item.unit ? ` (${item.unit})` : ""}</option>)}
            </select>
          </label>
          {meta && <label className="flex flex-col gap-2 text-body font-medium">{meta.label}{meta.unit ? ` (${meta.unit})` : ""}
            {meta.type === "bool" ? <select required className={control} value={raw} onChange={(e) => setRaw(e.target.value)}>
              <option value="">Choose</option><option value="true">Yes</option><option value="false">No</option>
            </select> : <input required value={raw} onChange={(e) => setRaw(e.target.value)} className={control}
              inputMode={["int", "float"].includes(meta.type) ? "decimal" : "text"} />}
            {meta.type === "list" && <span className="text-meta font-normal text-text-muted">Separate items with commas. Enter [] only if explicitly none.</span>}
          </label>}
          {error && <p role="alert" className="text-body text-high-fg">{error}</p>}
          <div className="flex justify-end gap-3"><Button disabled={busy} onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" size="lg" disabled={disabled || busy || !meta || !raw.trim()}>{busy ? "Saving…" : "Save entry"}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  </>;
}
