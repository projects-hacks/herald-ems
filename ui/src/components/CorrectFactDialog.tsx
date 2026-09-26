import { Pencil } from "lucide-react";
import { useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { factValue } from "@/lib/format";
import type { FactValue, FactView } from "@/lib/types";
import { Button } from "@/components/kit";
import { useContract } from "@/lib/contract";
import { manualValue } from "@/lib/manual";
import { useHerald } from "@/lib/store";

function inputValue(value: FactValue) {
  return Array.isArray(value) ? value.length ? value.join(", ") : "[]" : value === null ? "" : String(value);
}

function parseValue(raw: string, old: FactValue): FactValue {
  if (Array.isArray(old)) return raw.split(",").map((item) => item.trim()).filter(Boolean);
  if (typeof old === "number") {
    const value = Number(raw);
    if (!Number.isFinite(value)) throw new Error("Enter a valid number.");
    return value;
  }
  if (typeof old === "boolean") {
    if (/^(yes|true|1)$/i.test(raw.trim())) return true;
    if (/^(no|false|0)$/i.test(raw.trim())) return false;
    throw new Error("Enter yes or no.");
  }
  return raw.trim();
}

/** `iconOnly` is the record-row form: a 48px pencil named "Correct <field>" for screen readers, so a long list of
 *  facts does not repeat the word "Correct" on every line. */
export function CorrectFactDialog({ fact, compact = false, iconOnly = false }: { fact: FactView; compact?: boolean; iconOnly?: boolean }) {
  const contract = useContract();
  const unavailable = useHerald((s) => s.stale || s.conn !== "open" || s.source === "fixture");
  const currentId = useHerald((s) => s.snapshot?.facts[fact.key]?.id);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(inputValue(fact.value));
  const [error, setError] = useState("");
  useEffect(() => { if (open) { setValue(inputValue(fact.value)); setError(""); } }, [open, fact.value]);
  const save = async () => {
    if (unavailable || currentId !== fact.id) { setError("This field changed or the connection was lost. Close and review the current record."); return; }
    try {
      const meta = contract?.keys[fact.key];
      const parsed = meta ? manualValue(value, meta) : parseValue(value, fact.value);
      if (parsed === "") throw new Error("Enter the corrected value.");
      if (await api.correct(fact.id, parsed)) setOpen(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Check this value."); }
  };
  return <>
    {iconOnly
      ? <Button disabled={unavailable} size="sm" variant="ghost" className="min-w-12 px-0" aria-label={`Correct ${fact.label}`} title={`Correct ${fact.label}`}
          onClick={() => setOpen(true)}><Pencil size={16} aria-hidden /></Button>
      : <Button disabled={unavailable} size={compact ? "sm" : "md"} variant="ghost" onClick={() => setOpen(true)}><Pencil size={14} />Correct</Button>}
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogTitle>Correct {fact.label}</DialogTitle>
        <DialogDescription>The original “{factValue(fact)}” stays in the audit trail as rejected. Saving confirms the correction and may send it to the authorized receiving system. For a new measurement, use Manual entry instead.</DialogDescription>
        {fact.provenance.audio_id && <audio controls src={`/api/audio/${fact.provenance.audio_id}`} aria-label="Original audio" />}
        {fact.provenance.photo_id && <a className="text-herald-accent underline" target="_blank" rel="noreferrer" href={`/api/photo/${fact.provenance.photo_id}`}>Open source photo</a>}
        <label className="mt-3 flex flex-col gap-1.5 text-meta font-semibold text-text-secondary">Correct value
          <input autoFocus value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void save(); }}
            className="h-12 rounded-[var(--radius-control)] border border-border-control bg-surface-2 px-3 text-critical text-text-primary" />
        </label>
        {Array.isArray(fact.value) && <p className="text-meta text-text-muted">Separate items with commas. Enter [] only if explicitly none.</p>}
        {error && <p role="alert" className="text-meta font-semibold text-high-fg">{error}</p>}
        <DialogFooter>
          <Button size="lg" onClick={() => setOpen(false)}>Cancel</Button>
          <ActionButton pendingKey={`correct:${fact.id}`} onClick={save} busyText="Saving…" variant="primary">Save and confirm</ActionButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>;
}
