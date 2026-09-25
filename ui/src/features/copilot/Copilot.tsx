// The copilot screen's own regions: the presence pill, what Herald did, how the
// patient moved, and what the ED has. Everything here is a clinical outcome or an action; system status appears
// only when something has stopped working.
import { ArrowDownRight, ArrowUpRight, BookOpenCheck, Download, Ear, FileText, Share2, UserRound, Monitor, Pause, Play, RotateCcw, Send, ShieldCheck, SkipForward, TriangleAlert } from "lucide-react";
import type { FixturePlayer } from "@/lib/ws";
import type { ProtocolCue } from "@/lib/types";
import { api } from "@/lib/api";
import { activity, cuePoints, edHas, patientKnown, SAFETY_KEYS, type ActivityKind, type Presence } from "@/lib/copilot";
import { GROUPS } from "@/lib/selectors";
import { clockSeconds, factValue, hhmmss } from "@/lib/format";
import { useNow } from "@/hooks/useNow";
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

const KIND_ICON: Record<ActivityKind, typeof Ear> = { heard: Ear, read: Monitor, checked: ShieldCheck, found: BookOpenCheck, sent: Send };

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
  const destFact = s.facts["transport.destination"];
  const dest = ed.destination ?? (destFact?.status === "confirmed" ? String(destFact.value) : null);
  return <section className="copilot-ed" aria-labelledby="ed-h">
    <h2 id="ed-h">{ed.destination ? `${ed.destination} has` : "The ED has"}</h2>
    {!ed.configured ? <p>No receiving ED set for this vehicle.</p> : !ed.authorized ? <p>Nothing yet — sharing not authorized. Confirmed facts stay on this vehicle.</p>
      : ed.sent.length ? <p className="ed-sent">{ed.sent.slice(0, 8).join(" · ")}{ed.sent.length > 8 ? ` · +${ed.sent.length - 8} more` : ""}</p>
      : <p>Nothing sent yet.</p>}
    {ed.lastAck && <p className="ed-meta">Last received {hhmm(ed.lastAck)}{s.relay.link === "down" ? " · link down, updates held" : ""}</p>}
    {ed.waiting > 0 && <p className="ed-meta">{ed.waiting} captured {ed.waiting === 1 ? "fact waits" : "facts wait"} for your confirmation before sending</p>}
    <div className="ed-actions">
      {ed.configured && !ed.authorized && <ActionButton pendingKey="authorize" variant="primary" className="min-h-16"
        busyText="Sharing…" onClick={() => api.authorize(dest ?? "Receiving ED")}><Share2 size={19} />Share with {dest ?? "the ED"}</ActionButton>}
      <button className="cabin-button" onClick={onHandoff}><FileText size={19} />Handoff report</button>
      <a className="cabin-button" href="/api/handoff/fhir" download={`herald-${s.incident.id}.fhir.json`}><Download size={19} />Export (FHIR)</a>
    </div>
  </section>;
}

function Passage({ p }: { p: ProtocolCue["passages"][number] }) {
  return <figure>
    <blockquote>{p.text}</blockquote>
    <figcaption><strong>{p.doc === p.title || !p.title ? `Policy ${p.doc}` : `${p.doc} · ${p.title}`} §{p.section}</strong>
      {p.page ? <span> · p. {p.page}</span> : null}{p.effective ? <span> · effective {p.effective}</span> : null}
      {p.shortened && <span> · shortened</span>}{p.text_layer_uncertain && <span> · text layer uncertain, check the page</span>}</figcaption>
  </figure>;
}

/** The county's own words for the situation Herald recognised: quoted, cited, dated. Herald adds nothing. One passage
 *  per situation on the screen; the rest are a tap away. */
export function ProtocolCues({ onOpen }: { onOpen: () => void }) {
  const cues = useHerald((st) => st.snapshot?.protocol_cues);   // select the stored array: a fresh [] would re-render forever
  if (!cues?.length) return null;
  const shown = new Set<string>();                        // a passage appears once, under the first situation that found it
  return <section className="copilot-protocol" aria-labelledby="protocol-h">
    <h2 id="protocol-h"><BookOpenCheck size={16} aria-hidden />County protocol</h2>
    {cues.map((c) => <article key={c.id} className="protocol-cue" data-state={c.state}>
      <h3>{c.title}</h3>
      {c.state === "searching" && <p className="protocol-status" role="status">Finding the county passage…</p>}
      {c.state === "not_covered" && <p className="protocol-status">The county documents on this vehicle do not cover this.</p>}
      {c.state === "found" && (() => { const points = cuePoints(c, shown); return points.length ? <ul className="protocol-points">{points.map((k, i) => <li key={i}>
        <span>{k.segments.map((s, j) => s.hl ? <mark key={j}>{s.t}</mark> : <span key={j}>{s.t}</span>)}</span>
        <cite>{k.cite}</cite>
      </li>)}</ul> : <p className="protocol-status">No single rule to show here. The county text is below.</p>; })()}
      {c.state === "found" && <details className="protocol-more"><summary>County text · effective {c.passages[0]?.effective ?? "date not stated"}</summary>
        {c.passages.map((p) => <Passage key={`${p.doc}-${p.section}`} p={p} />)}</details>}
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

/** What Herald knows so far: fields appear as they are heard or read. Unconfirmed values say so; the newest glows. */
export function PatientKnown({ onRecord }: { onRecord: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const now = useNow();
  if (!s) return null;
  const groups = patientKnown(s, GROUPS);
  if (!groups.length) return <section className="copilot-known glass-1" aria-labelledby="known-h"><h2 id="known-h"><UserRound size={16} aria-hidden />Patient</h2>
    <p className="activity-empty">Nothing heard yet. Details appear here as they are said.</p></section>;
  return <section className="copilot-known glass-1" aria-labelledby="known-h">
    <h2 id="known-h"><UserRound size={16} aria-hidden />Patient</h2>
    {groups.map((g) => <div key={g.name} className="known-group" data-group={g.name}>
      <h3>{g.name}</h3>
      <dl>{g.facts.map((f) => <div key={f.id} data-status={f.status} data-safety={SAFETY_KEYS.includes(f.key) || undefined}
        data-new={now - Date.parse(f.ts) < 20000 || undefined}>
        <dt>{f.label}</dt><dd>{factValue(f)}{f.status === "unconfirmed" && <small>not confirmed</small>}</dd>
      </div>)}</dl>
    </div>)}
    <button className="activity-all" onClick={onRecord}>Sources</button>
  </section>;
}

const span = (sec: number) => { const m = Math.floor(Math.abs(sec) / 60); return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} m` : `${m} min`; };

/** The situation at a glance, under the patient line: how ready each pre-alert is (and what it still lacks), and the
 *  clocks that are running. Readiness is gap-first: the missing items are named, not counted. */
export function SituationBar() {
  const s = useHerald((st) => st.snapshot);
  const at = useHerald((st) => st.lastStateAt);
  const now = useNow();
  if (!s || (!s.readiness.length && !s.clocks.some((c) => c.id !== "scene"))) return null;
  const clock = (id: string) => s.clocks.find((c) => c.id === id);
  const lkw = clock("lkw"), eta = clock("eta"), due = clock("reassess");
  return <div className="situation-bar" role="group" aria-label="Situation">
    {s.readiness.map((r) => {
      const missing = r.items.filter((i) => i.state !== "done").map((i) => i.label);
      return <span key={r.id} className="sit-ready" data-ready={r.ready || undefined}>
        <b>{r.label}</b>
        <span className="sit-meter" aria-hidden>{r.items.map((i) => <i key={i.key} data-state={i.state} />)}</span>
        <span className="num">{r.done} of {r.total}</span>
        {r.ready ? <em>ready</em> : missing.length ? <em>missing {missing.slice(0, 2).join(", ").toLowerCase()}{missing.length > 2 ? ` +${missing.length - 2}` : ""}</em> : null}
      </span>;
    })}
    {lkw && <span className="sit-clock"><b>LKW</b> {lkw.label.replace(/^LKW\s*/, "")} <span className="num">+{span(clockSeconds(lkw, at, now))}</span></span>}
    {eta && (() => { const left = clockSeconds(eta, at, now); return <span className="sit-clock"><b>ETA</b> <span className="num">{left > 0 ? hhmmss(left).replace(/^00:/, "") : "arriving"}</span></span>; })()}
    {due && (() => { const left = clockSeconds(due, at, now); return <span className="sit-clock" data-overdue={left <= 0 || undefined}><b>Vitals</b>
      <span className="num">{left > 0 ? `due in ${hhmmss(left).replace(/^00:/, "")}` : "due now"}</span></span>; })()}
  </div>;
}
