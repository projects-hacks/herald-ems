// Where the ambulance is going, in the situation bar. The destination is set by voice or by one tap, never picked
// from a list in the main flow (owner, 2026-09-26): the crew's words that name one county hospital set it (Herald
// says so: "heard"); while none is set, Herald suggests ONE hospital from the county's own destination rules with a
// single Accept, and saying the hospital accepts it too. Words that name no single county hospital stay visible as
// heard. The county list is one small "Other hospital…" link away for the rare manual case.
import { MapPin, Sparkles } from "lucide-react";
import { ActionButton } from "@/components/ActionButton";
import { api } from "@/lib/api";
import { useHerald } from "@/lib/store";
import type { Snapshot, TransportSuggestion, TransportView } from "@/lib/types";

const HOW: Record<string, string> = { suggested: "Herald suggested, accepted", chosen: "chosen" };

/** How the destination was set, in words: "heard “Regional”", "Herald suggested, accepted", "chosen". */
export function destinationHow(d: NonNullable<TransportView["destination"]>): string {
  if (d.how === "heard") return d.said && d.said !== d.value ? `heard “${d.said}”` : "heard";
  return HOW[d.how] ?? d.how;
}

/** "Comprehensive Stroke Center, 9 min by road" / "… · no location — nearest not known". */
export function suggestionDetail(sg: TransportSuggestion, t: TransportView): string {
  const what = sg.basis === "heard" ? sg.situation : sg.service ?? "";
  if (sg.minutes !== null) return `${what}, ${sg.minutes} min by road`;
  const why = !t.position || !t.position.fresh ? "no location" : "no road route";
  return `${what} · ${why} — nearest not known`;
}

export function Suggestion({ s }: { s: Snapshot }) {
  const t = s.transport, sg = t?.suggestion;
  if (!t || !sg) return null;
  return <div className="sit-suggestion" role="group" aria-label="Herald's destination suggestion">
    <Sparkles size={18} aria-hidden className="sit-suggestion-icon" />
    <div className="sit-suggestion-text">
      <p>Herald suggests <b>{sg.name}</b> — {suggestionDetail(sg, t)}</p>
      {sg.basis === "policy" && <small>{sg.situation} · {sg.cite}{sg.note ? ` · ${sg.note}` : ""} · diversion status not known</small>}
      <small>Accept, or say the hospital</small>
    </div>
    <ActionButton pendingKey={`destination:${sg.id}`} variant="primary" className="min-h-16" busyText="Setting…"
      onClick={() => api.setDestination(sg.id, "suggestion")}>Accept</ActionButton>
  </div>;
}

/** The destination chip (or what was heard), the suggestion while none is set, and the manual link. */
export function DestinationStatus({ s }: { s: Snapshot }) {
  const setUi = useHerald((st) => st.setUi);
  const t = s.transport;
  if (!t || s.incident.disposition || s.incident.arrived_at || s.incident.transferred_at) return null;
  const d = t.destination, h = t.heard;
  const minutes = d?.id ? t.options.find((o) => o.id === d.id)?.minutes ?? null : null;
  const unmatched = h && h.state !== "matched";
  return <>
    {d ? <span className="sit-clock sit-dest" aria-label={`Destination ${d.value}, ${destinationHow(d)}${minutes !== null ? `, ${minutes} minutes by road` : ""}`}>
      <MapPin size={16} aria-hidden /><b>To</b><span>{d.value}{minutes !== null && <span className="num"> · {minutes} min</span>}</span>
      <small className="sit-source">{destinationHow(d)}</small>
    </span> : !t.suggestion && !unmatched && <span className="sit-clock" data-unconfirmed><b>To</b><span>say the hospital</span></span>}
    {unmatched && <span className="sit-clock sit-heard" data-unconfirmed role="status">
      <b>Heard</b><span>“{h.value}”{h.state === "matching" ? " · matching to the county list…" : " — not matched to a county hospital"}</span>
    </span>}
    {t.options.length > 0 && <button type="button" className="sit-other" onClick={() => setUi({ destinationOpen: true })}>Other hospital…</button>}
    <Suggestion s={s} />
  </>;
}
