// Choosing where the ambulance goes: the county's receiving hospitals (Policy 602 Table B), nearest by road first when
// the vehicle's position is known, with the designations the county lists. What Herald heard is offered as a
// suggestion; the medic's tap is the destination. Herald recommends none: live diversion and bed status are not
// available on the vehicle, and the screen says so.
import { Check, MapPin } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useHerald } from "@/lib/store";
import type { Snapshot, TransportView } from "@/lib/types";

export function routingNote(t: TransportView): string | null {
  if (!t.routing) return "Road routing is not set up on this vehicle. The ETA is the crew's estimate.";
  if (t.router_error) return "Road routing is unavailable right now. The ETA is the crew's estimate.";
  if (!t.position) return "Drive times appear once this tablet shares its location (Settings).";
  if (!t.position.fresh) return "The vehicle's location is out of date. Drive times are hidden until it updates.";
  return null;
}

function strokeCall(s: Snapshot): boolean {
  return s.readiness.some((r) => r.id === "stroke") || s.alerts.some((a) => a.type === "gfast_positive" || a.type === "race_positive");
}

export function DestinationDialog() {
  const open = useHerald((st) => st.ui.destinationOpen);
  const s = useHerald((st) => st.snapshot);
  const setUi = useHerald((st) => st.setUi);
  const t = s?.transport;
  if (!s || !t) return null;
  const close = () => setUi({ destinationOpen: false });
  const pick = async (id: string) => { if (await api.setDestination(id)) close(); };
  const d = t.destination;
  const suggested = d?.suggested ? t.options.find((o) => o.id === d.suggested) : undefined;
  const stroke = strokeCall(s);
  const note = routingNote(t);
  return <Dialog open={open} onOpenChange={(o) => setUi({ destinationOpen: o })}>
    <DialogContent className="destination-dialog">
      <DialogTitle>Destination</DialogTitle>
      <DialogDescription>County receiving hospitals{t.position?.fresh && !t.router_error ? ", nearest by road first" : ""}. Your tap sets the destination.</DialogDescription>
      {d && d.status === "unconfirmed" && !d.id && <div className="destination-heard" role="status">
        {suggested ? <><span>Heard “{d.value}”</span><button className="cabin-button primary" onClick={() => void pick(suggested.id)}>
          <Check size={18} aria-hidden />{suggested.name}</button></>
          : d.matching ? <span>Heard “{d.value}”. Matching it to the county list…</span>
          : <span>Heard “{d.value}”. It does not name one hospital on the county list; choose below.</span>}
      </div>}
      <ul className="destination-list">
        {t.options.map((o) => {
          const chosen = d?.status === "confirmed" && d.id === o.id;
          return <li key={o.id}><button className="destination-row" aria-pressed={chosen} onClick={() => void pick(o.id)}>
            <span className="destination-name">{chosen && <Check size={18} aria-hidden />}{o.name}</span>
            <span className="destination-tags">{o.designations.map((g) => <span key={g} className="destination-tag"
              data-relevant={(stroke && /stroke/i.test(g)) || undefined}>{g}</span>)}</span>
            <span className="destination-time num">{o.minutes !== null ? `${o.minutes} min · ${o.km} km` : ""}</span>
          </button></li>;
        })}
      </ul>
      {!t.options.length && <p>This county has no receiving hospital list on the vehicle.</p>}
      {note && <p className="destination-note"><MapPin size={16} aria-hidden />{note}</p>}
      <p className="destination-note">Diversion and bed status are not available on the vehicle. Confirm with the hospital.</p>
      <DialogFooter><button className="cabin-button" onClick={close}>Close</button></DialogFooter>
    </DialogContent>
  </Dialog>;
}
