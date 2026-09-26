// The hand over action, always in reach at the bottom of the handoff: one primary button and a confirmation that says
// exactly what happens (what stays out of the report, that listening stops and this patient's media is deleted).
import { useState } from "react";
import { Download, HeartHandshake } from "lucide-react";
import { ActionNote, usePendingAction } from "@/components/ActionButton";
import { Button } from "@/components/kit";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useNow } from "@/hooks/useNow";
import { handoverDestination, handoverDue } from "@/lib/handover";
import { allFacts } from "@/lib/selectors";
import { useHerald } from "@/lib/store";
import { cn } from "@/lib/utils";
import type { HandoffReportData, Snapshot } from "@/lib/types";
import { downloadReport } from "./HandoffReport";
import "./handoff.css";

/** Now's header entry to the handoff: quiet during the call, the primary style once the crew has arrived or the ETA
 *  is five minutes or less. Gone once the patient is handed over (Now then shows the done state). */
export function HandoverHeaderButton({ pressed, onOpen }: { pressed: boolean; onOpen: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const at = useHerald((st) => st.lastStateAt);
  const now = useNow();
  if (!s || s.incident.handed_over_at || s.incident.ended_at) return null;
  const due = handoverDue(s, at, now);
  return <button className={cn("cabin-button handover-button", due && "primary")} aria-label="Hand over" aria-pressed={pressed}
    data-due={due || undefined} onClick={onOpen}><HeartHandshake size={19} aria-hidden /><span className={due ? undefined : "patients-button-label"}>Hand over</span></button>;
}

export function HandoverBar({ s, report, missing }: { s: Snapshot; report: HandoffReportData | null; missing: number }) {
  const [open, setOpen] = useState(false);
  const p = usePendingAction("handover");
  const dest = handoverDestination(s);
  const unconfirmed = allFacts(s).filter((f) => f.status === "unconfirmed").length;
  const title = dest ? `Hand over to ${dest}` : "Hand over";
  const confirm = async () => { if (await api.handover(dest)) setOpen(false); };
  return <div className="handover-bar" role="region" aria-label="Hand over">
    <Button size="lg" aria-label="Export report as text" disabled={!report} onClick={() => report && downloadReport(report)}>
      <Download size={18} aria-hidden />Export</Button>
    <Button variant="primary" className="handover-primary" disabled={p.replay} title={p.replay ? "Replay: actions are off" : undefined}
      onClick={() => setOpen(true)}><HeartHandshake size={22} aria-hidden />{title}</Button>
    <Dialog open={open} onOpenChange={(o) => { if (!p.busy) setOpen(o); }}><DialogContent>
      <DialogTitle>{title}?</DialogTitle>
      <DialogDescription>
        {unconfirmed > 0 && `${unconfirmed} unconfirmed ${unconfirmed === 1 ? "item won't" : "items won't"} be included. `}
        {missing > 0 && `${missing} required ${missing === 1 ? "item is" : "items are"} not recorded. `}
        Listening stops and this patient's audio and photos are deleted.
      </DialogDescription>
      <ActionNote a={p} />
      <DialogFooter>
        <Button size="lg" disabled={p.busy} onClick={() => setOpen(false)}>Cancel</Button>
        <Button variant="primary" disabled={p.disabled} onClick={() => void confirm()}>{p.busy ? "Handing over…" : "Hand over"}</Button>
      </DialogFooter>
    </DialogContent></Dialog>
  </div>;
}
