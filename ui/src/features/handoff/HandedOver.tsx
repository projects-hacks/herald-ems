// Done: the patient is handed over. Says where and when, whether the ED has the final report, and offers the next
// patient. Shown on Now and on the handoff; capture stays off until the next patient's record exists.
import { CircleCheck, FileText, UserPlus } from "lucide-react";
import { ActionButton } from "@/components/ActionButton";
import { Button } from "@/components/kit";
import { api } from "@/lib/api";
import { hhmm } from "@/lib/format";
import { handoverDelivery, handoverDestination } from "@/lib/handover";
import "./handoff.css";
import { useHerald } from "@/lib/store";
import type { Snapshot } from "@/lib/types";

export function HandedOver({ s, reportOpen, onViewReport }: { s: Snapshot; reportOpen?: boolean; onViewReport: () => void }) {
  const setUi = useHerald((st) => st.setUi);
  const dest = handoverDestination(s);
  const ed = handoverDelivery(s);
  // A new incident switches the snapshot, and the screen returns to Now on its own (store.setSnapshot).
  // already ended by the hand over, with its outcome recorded ("transported"): nothing more to choose
  const next = async () => { if (await api.newIncident(null, null)) setUi({ page: "overview", incidentPhase: "scene" }); };
  return <section className="handed-over" aria-labelledby="handed-over-h">
    <CircleCheck size={32} aria-hidden className="handed-over-icon" />
    <div className="handed-over-body">
      <h2 id="handed-over-h">Handed over{dest ? ` to ${dest}` : ""} · <span className="num">{hhmm(s.incident.handed_over_at)}</span></h2>
      <p className="handoff-chip" data-tone={ed.tone} role="status">{ed.text}</p>
      <p className="handed-over-note">Listening and the camera are off. This patient's audio and photos are deleted; the confirmed record stays in Previous encounters.</p>
      <div className="handed-over-actions">
        <ActionButton pendingKey="incident" variant="primary" busyText="Starting…" onClick={() => void next()}><UserPlus size={20} aria-hidden />Start next patient</ActionButton>
        <Button size="lg" aria-expanded={reportOpen} onClick={onViewReport}><FileText size={18} aria-hidden />View handed-over report</Button>
      </div>
    </div>
  </section>;
}
