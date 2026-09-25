// The copilot screen's own regions: the presence pill, what Herald did, how the
// patient moved, and what the ED has. Everything here is a clinical outcome or an action; system status appears
// only when something has stopped working.
import { ArrowDownRight, ArrowUpRight, BookOpenCheck, Ear, FileText, Monitor, Pause, Play, RotateCcw, Send, ShieldCheck, SkipForward, TriangleAlert } from "lucide-react";
import type { FixturePlayer } from "@/lib/ws";
import { api } from "@/lib/api";
import { activity, edHas, type ActivityKind, type Presence } from "@/lib/copilot";
import { useContract } from "@/lib/contract";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { Sparkline } from "@/components/Sparkline";
import { ActionButton } from "@/components/ActionButton";

export function PresencePill({ p }: { p: Presence }) {
  return <span className="presence-pill" data-tone={p.tone} role={p.tone === "down" ? "alert" : "status"}>
    {p.tone === "down" ? <TriangleAlert size={16} aria-hidden /> : <span className="presence-dot" aria-hidden />}{p.text}
  </span>;
}

const KIND_ICON: Record<ActivityKind, typeof Ear> = { heard: Ear, read: Monitor, checked: ShieldCheck, sent: Send };

export function HeraldActivity({ onAll }: { onAll: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const working = s?.transcripts.some((t) => t.trace?.model?.status === "running");
  const contract = useContract();
  const lines = s ? activity(s, 6, (k) => contract?.keys[k]?.label ?? k.split(".").at(-1)!.replace(/_/g, " ")) : [];
  return <section className="copilot-activity" aria-labelledby="activity-h">
    <h2 id="activity-h">Herald is doing</h2>
    {working && <p className="activity-working" role="status">Listening… working on what was just said</p>}
    {lines.length ? <ol>{lines.map((l) => { const Icon = KIND_ICON[l.kind]; return <li key={l.id} data-kind={l.kind}>
      <time>{hhmm(l.ts)}</time><Icon size={16} aria-hidden /><span>{l.text}</span>
    </li>; })}</ol> : !working && <p className="activity-empty">Nothing yet. Start listening and Herald records as you work.</p>}
    {lines.length > 0 && <button className="activity-all" onClick={onAll}>Full record</button>}
  </section>;
}

export function MovementStrip({ onTrends }: { onTrends: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const contract = useContract();
  const moved = (s?.changed ?? []).filter((c) => c.significant || c.unconfirmed);
  if (!s) return null;
  return <section className="copilot-movement" aria-labelledby="movement-h">
    <h2 id="movement-h">How the patient is moving</h2>
    {moved.length ? <ul>{moved.map((c) => {
      const minutes = c.times.length > 1 ? Math.round((Date.parse(c.times.at(-1)!) - Date.parse(c.times[0])) / 60000) : 0;
      return <li key={c.key}>
        {c.direction === "down" ? <ArrowDownRight size={20} aria-hidden /> : <ArrowUpRight size={20} aria-hidden />}
        <strong>{c.label} {c.series.join(" → ")}{contract?.keys[c.key]?.unit ? ` ${contract.keys[c.key].unit}` : ""}</strong>
        <span>{minutes ? `over ${minutes} min` : hhmm(c.times.at(-1))}</span>
        <Sparkline values={c.series} width={96} height={28} label={`${c.label} trend`} />
        {c.unconfirmed && c.unconfirmed_fact_ids?.length ? <ActionButton pendingKey={`confirm-many:${c.unconfirmed_fact_ids.slice().sort().join(",")}`}
          onClick={() => api.confirmMany(c.unconfirmed_fact_ids!)} busyText="Saving…">Confirm latest reading</ActionButton> : null}
        {c.unconfirmed && <small>Unconfirmed reading — not sent to the ED</small>}
      </li>; })}</ul> : <p>No change in confirmed readings so far.</p>}
    <button className="activity-all" onClick={onTrends}>Trends</button>
  </section>;
}

export function EdCard({ onHandoff }: { onHandoff: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const contract = useContract();
  if (!s) return null;
  const ed = edHas(s, (k) => contract?.keys[k]?.label ?? k);
  return <section className="copilot-ed" aria-labelledby="ed-h">
    <h2 id="ed-h">{ed.destination ? `${ed.destination} has` : "The ED has"}</h2>
    {!ed.configured ? <p>No receiving ED set for this vehicle.</p> : !ed.authorized ? <p>Nothing yet — sharing not authorized. Confirmed facts stay on this vehicle.</p>
      : ed.sent.length ? <p className="ed-sent">{ed.sent.slice(0, 8).join(" · ")}{ed.sent.length > 8 ? ` · +${ed.sent.length - 8} more` : ""}</p>
      : <p>Nothing sent yet.</p>}
    {ed.lastAck && <p className="ed-meta">Last received {hhmm(ed.lastAck)}{s.relay.link === "down" ? " · link down, updates held" : ""}</p>}
    {ed.waiting > 0 && <p className="ed-meta">{ed.waiting} captured {ed.waiting === 1 ? "fact waits" : "facts wait"} for your confirmation before sending</p>}
    <button className="cabin-button" onClick={onHandoff}><FileText size={19} />Handoff report</button>
  </section>;
}

/** The county's own words for the situation Herald recognised: quoted, cited, dated. Herald adds nothing. */
export function ProtocolCues({ onOpen }: { onOpen: () => void }) {
  const cues = useHerald((st) => st.snapshot?.protocol_cues);   // select the stored array: a fresh [] would re-render forever
  if (!cues?.length) return null;
  return <section className="copilot-protocol" aria-labelledby="protocol-h">
    <h2 id="protocol-h"><BookOpenCheck size={16} aria-hidden />County protocol</h2>
    {cues.map((c) => <article key={c.id} className="protocol-cue" data-state={c.state}>
      <h3>{c.title}</h3>
      {c.state === "searching" && <p className="protocol-status" role="status">Finding the county passage…</p>}
      {c.state === "not_covered" && <p className="protocol-status">The county documents on this vehicle do not cover this.</p>}
      {c.passages.map((p) => <figure key={`${p.doc}-${p.section}`}>
        <blockquote>{p.text}</blockquote>
        <figcaption><strong>{p.doc === p.title || !p.title ? `Policy ${p.doc}` : `${p.doc} · ${p.title}`} §{p.section}</strong>
          {p.page ? <span> · p. {p.page}</span> : null}{p.effective ? <span> · effective {p.effective}</span> : null}
          {p.shortened && <span> · shortened</span>}{p.text_layer_uncertain && <span> · text layer uncertain, check the page</span>}</figcaption>
      </figure>)}
    </article>)}
    <button className="activity-all" onClick={onOpen}>All protocols</button>
  </section>;
}

/** A recorded scenario's transport controls, only in replay. */
export function ReplayBar({ player }: { player: FixturePlayer }) {
  const fixture = useHerald((st) => st.fixture);
  if (!fixture) return null;
  return <div className="copilot-replay" role="group" aria-label="Recorded scenario">
    <span>Scenario <b>{fixture.index}/{fixture.total}</b></span>
    <button onClick={() => fixture.playing ? player.pause() : player.play()} aria-label={fixture.playing ? "Pause replay" : "Play replay"}>{fixture.playing ? <Pause size={18} /> : <Play size={18} />}</button>
    <button onClick={() => player.step()} aria-label="Next recorded message"><SkipForward size={18} /></button>
    <button onClick={() => player.restart()} aria-label="Restart replay"><RotateCcw size={18} /></button>
  </div>;
}
