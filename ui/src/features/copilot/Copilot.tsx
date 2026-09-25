// The copilot screen's own regions: the presence pill, what Herald did, how the
// patient moved, and what the ED has. Everything here is a clinical outcome or an action; system status appears
// only when something has stopped working.
import { ArrowDownRight, ArrowUpRight, BookOpenCheck, Download, Ear, FileText, Share2, Monitor, Pause, Play, RotateCcw, Send, ShieldCheck, SkipForward, TriangleAlert } from "lucide-react";
import type { FixturePlayer } from "@/lib/ws";
import type { ProtocolCue } from "@/lib/types";
import { api } from "@/lib/api";
import { activity, cuePoints, edHas, keyPoints, setAside, patientKnown, SAFETY_KEYS, type ActivityKind, type Presence } from "@/lib/copilot";
import { GROUPS } from "@/lib/selectors";
import { clockSeconds, factValue, hhmmss } from "@/lib/format";
import { useNow } from "@/hooks/useNow";
import { useContract } from "@/lib/contract";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import { Sparkline } from "@/components/Sparkline";
import { ActionButton, ActionNote, usePendingAction } from "@/components/ActionButton";

/** The whole system status, and the one capture control: tap to pause or resume listening and watching. */
export function PresencePill({ p, paused, disabled, onToggle }: { p: Presence; paused: boolean; disabled?: boolean; onToggle: () => void }) {
  const live = p.tone === "ok";
  return <button type="button" className="presence-pill" data-tone={p.tone} disabled={disabled} onClick={onToggle}
    aria-label={live && !paused ? "Pause listening" : "Start listening"}>
    {p.tone === "down" ? <TriangleAlert size={16} aria-hidden /> : <span className="presence-dot" aria-hidden />}
    <span role={p.tone === "down" ? "alert" : "status"}>{paused ? "Paused — tap to listen and watch" : p.text}</span>
  </button>;
}

const KIND_ICON: Record<ActivityKind, typeof Ear> = { heard: Ear, read: Monitor, checked: ShieldCheck, found: BookOpenCheck, sent: Send };

/** What Herald heard, read, checked, found and sent, newest first. Not a clinical view, so it lives on the Record
 *  page (the What Herald did tab) rather than on Now; `onAll` adds a link when it is shown as a summary. */
export function HeraldActivity({ onAll, limit = 6 }: { onAll?: () => void; limit?: number }) {
  const s = useHerald((st) => st.snapshot);
  const contract = useContract();
  const name = (k: string) => contract?.keys[k]?.label ?? (k.startsWith("score.") ? (s?.scores as unknown as Record<string, { name?: string } | undefined> | undefined)?.[k.slice(6)]?.name : undefined)
    ?? (k.startsWith("alert.") ? "pre-alert status" : k.split(".").at(-1)!.replace(/_/g, " "));
  const lines = s ? activity(s, limit, name) : [];
  return <section className="copilot-activity" aria-labelledby="activity-h">
    <h2 id="activity-h">What Herald did</h2>
    {lines.length ? <ol className="herald-timeline">{lines.map((l) => { const Icon = KIND_ICON[l.kind]; return <li key={l.id} data-kind={l.kind}>
      <span className="tl-node" aria-hidden><Icon size={14} /></span>
      <span className="tl-body"><span className="tl-text">{l.text}</span>{l.detail && <span className="tl-detail">{l.detail}</span>}</span>
      <time>{hhmm(l.ts)}</time>
    </li>; })}</ol> : <p className="activity-empty">Nothing yet. Herald records what it hears, reads and sends here.</p>}
    {s && setAside(s) > 0 && <p className="activity-aside">Set aside {setAside(s)} {setAside(s) === 1 ? "remark" : "remarks"} with nothing clinical in {setAside(s) === 1 ? "it" : "them"}</p>}
    {lines.length > 0 && onAll && <button className="activity-all" onClick={onAll}>Full record</button>}
  </section>;
}

export function MovementStrip({ onTrends }: { onTrends: () => void }) {
  const s = useHerald((st) => st.snapshot);
  const contract = useContract();
  if (!s) return null;
  // Show a vital here when it MOVED (significant), when a reading is WAITING (unconfirmed), or when its latest value
  // is OUT OF RANGE (severity) even though it did not move -- the last case is the UI-review fix: a dangerous-but-
  // steady value used to be silent on this panel. Severity is backend-computed and already withdrawn for patients
  // the adult ranges do not fit (children, pregnancy), so this panel inherits that scope for free.
  const moved = s.changed.filter((c) => c.significant || c.unconfirmed || c.severity);
  const shownKeys = new Set(moved.map((c) => c.key));
  // A vital with only one reading has no trend row, so an abnormal single reading would be missed. Pick those up
  // from the confirmed facts: latest value carries severity, not already shown as a trend.
  const abnormalStill = Object.values(s.facts).filter(
    (f) => f.severity && f.key.startsWith("vitals.") && f.status === "confirmed" && !shownKeys.has(f.key));
  const anything = moved.length > 0 || abnormalStill.length > 0;
  return <section className="copilot-movement" aria-labelledby="movement-h">
    <h2 id="movement-h">How the patient is moving</h2>
    {anything ? <ul>{[
      ...moved.map((c) => {
        const minutes = c.times.length > 1 ? Math.round((Date.parse(c.times.at(-1)!) - Date.parse(c.times[0])) / 60000) : 0;
        const unit = contract?.keys[c.key]?.unit ? ` ${contract.keys[c.key].unit}` : "";
        return <li key={c.key} data-severity={c.severity} aria-label={c.severity ? `${c.label}, ${c.severity}` : undefined}>
          {c.direction === "down" ? <ArrowDownRight size={20} aria-hidden /> : <ArrowUpRight size={20} aria-hidden />}
          <strong>{c.label} {c.series.join(" → ")}{unit}</strong>
          {c.severity && <SeverityTag severity={c.severity} />}
          <span>{minutes ? `over ${minutes} min` : hhmm(c.times.at(-1))}</span>
          <Sparkline values={c.series} width={96} height={28} label={`${c.label} trend`} />
          {c.unconfirmed && c.unconfirmed_fact_ids?.length ? <ActionButton pendingKey={`confirm-many:${c.unconfirmed_fact_ids.slice().sort().join(",")}`}
            onClick={() => api.confirmMany(c.unconfirmed_fact_ids!)} busyText="Saving…">Confirm latest reading</ActionButton> : null}
          {c.unconfirmed && <small>Unconfirmed reading — not sent to the ED</small>}
        </li>;
      }),
      ...abnormalStill.map((f) => (
        <li key={f.key} data-severity={f.severity} aria-label={`${f.label}, ${f.severity}`}>
          <span className="movement-flat" aria-hidden>—</span>
          <strong>{f.label} {factValue(f)}</strong>
          <SeverityTag severity={f.severity!} />
          <span>steady · {hhmm(f.ts)}</span>
        </li>
      )),
    ]}</ul> : <p>No change in confirmed readings so far.</p>}
    <button className="activity-all" onClick={onTrends}>Trends</button>
  </section>;
}

/** A word + icon for a vital's severity, so this panel signals it the same way as the tiles, never colour alone. */
function SeverityTag({ severity }: { severity: "abnormal" | "critical" }) {
  return <span className="movement-severity" data-severity={severity}>
    <TriangleAlert size={13} aria-hidden />{severity === "critical" ? "critical" : "out of range"}
  </span>;
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
    {ed.lastAck && <p className="ed-meta">Last delivered {hhmm(ed.lastAck)} (system acknowledgement)</p>}
    {ed.authorized && s.relay.link === "down" && <p className="ed-link-down" role="status">Link to the ED is down — updates are held on this vehicle</p>}
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
export function ProtocolCues() {
  const cues = useHerald((st) => st.snapshot?.protocol_cues);   // select the stored array: a fresh [] would re-render forever
  if (!cues?.length) return null;
  const shown = new Set<string>();                        // a passage appears once, under the first situation that found it
  return <section className="copilot-protocol" aria-labelledby="protocol-h">
    <h2 id="protocol-h"><BookOpenCheck size={16} aria-hidden />County protocol</h2>
    <p className="protocol-note">Found by Herald in the county’s documents · quoted, not advice</p>
    {/* One card per recognised situation, side by side; the row scrolls sideways when there are more than fit, so
        the protocol takes one band of the screen instead of a tall column. Focusable, so a keyboard can scroll it. */}
    <div className="protocol-strip" tabIndex={0} aria-label="County passages, scroll sideways for more">
    {cues.map((c) => <article key={c.id} className="protocol-cue" data-state={c.state} data-asked={c.asked || undefined}>
      <h3>{c.asked ? <><span className="cue-asked">You asked</span>“{c.query}”</> : c.title}</h3>
      {c.state === "searching" && <p className="protocol-status" role="status">Finding the county passage…</p>}
      {c.state === "not_covered" && <p className="protocol-status">The county documents on this vehicle do not cover this.</p>}
      {c.state === "found" && (() => { let points = cuePoints(c, shown); let closest = false;
        if (!points.length && c.asked) { points = keyPoints(c.passages, 1); closest = points.length > 0; }   // asked: the nearest county words
        return points.length ? <>{closest && <p className="protocol-status">No rule names this exactly. The closest county text:</p>}<ul className="protocol-points">{points.map((k, i) => <li key={i}>
        <span>{k.segments.map((s, j) => s.hl ? <mark key={j}>{s.t}</mark> : <span key={j}>{s.t}</span>)}</span>
        <cite>{k.cite}</cite>
      </li>)}</ul></> : <p className="protocol-status">Closest county sections: {[...new Set(c.passages.slice(0, 3).map((p) => `${p.doc} §${p.section}`))].join(" · ")}</p>; })()}
      {c.state === "found" && <details className="protocol-more"><summary>Full county text{c.passages[0]?.effective ? ` · effective ${c.passages[0].effective}` : ""}</summary>
        {c.passages.map((p) => <Passage key={`${p.doc}-${p.section}`} p={p} />)}</details>}
    </article>)}
    </div>
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
/** The patient as one bar under the patient line, instead of its own card. Safety facts (allergies, anticoagulant,
 *  code status) lead as warning chips, because a medic must never have to look for them; the rest of the confirmed
 *  history follows as compact chips. Age, sex and complaint are in the patient line above, so they are not repeated.
 *  Confirmed facts only: an unconfirmed value waits in Needs you. Details opens Record -> Facts & sources. */
const IN_PATIENT_LINE = new Set(["patient.age", "patient.sex", "complaint.chief"]);
export function PatientBar({ onDetails, limit = 6 }: { onDetails: () => void; limit?: number }) {
  const s = useHerald((st) => st.snapshot);
  const now = useNow();
  if (!s) return null;
  const facts = patientKnown(s, GROUPS).flatMap((g) => g.facts).filter((f) => !IN_PATIENT_LINE.has(f.key));
  const safety = facts.filter((f) => SAFETY_KEYS.includes(f.key));
  const rest = facts.filter((f) => !SAFETY_KEYS.includes(f.key));
  const shown = [...safety, ...rest.slice(0, Math.max(0, limit - safety.length))];
  const more = facts.length - shown.length;
  return <div className="patient-bar" role="group" aria-label="Patient">
    {shown.length ? shown.map((f) => {
      const value = factValue(f);
      return <span key={f.id} className="patient-chip" data-safety={SAFETY_KEYS.includes(f.key) || undefined}
        data-new={now - Date.parse(f.ts) < 20000 || undefined} title={`${f.label}: ${value}`}>
        {SAFETY_KEYS.includes(f.key) && <TriangleAlert size={13} aria-hidden />}
        <b>{f.label}</b><span>{value}</span>
      </span>;
    }) : <span className="patient-empty">No history confirmed yet</span>}
    <Spo2Target />
    <button className="patient-details" onClick={onDetails}>{more > 0 ? `+${more} more · Details` : "Details"}</button>
  </div>;
}

/** The NEWS2 SpO2 target as a one-tap switch: 94-98% (Scale 1) or 88-92% for hypercapnic respiratory failure such as
 *  COPD (Scale 2). The tap is the clinician direction RCP requires, so it is written confirmed at once and re-bands
 *  the SpO2 colouring everywhere; switching back is the same tap. Shown once there is an SpO2 reading, and not for a
 *  patient the adult ranges do not fit (NEWS2 excluded: children, pregnancy), where no SpO2 colour is shown anyway. */
function Spo2Target() {
  const s = useHerald((st) => st.snapshot);
  const setting = s?.facts["patient.spo2_scale"];
  const scale2 = setting?.status === "confirmed" && Number(setting.value) === 2;
  const next: 1 | 2 = scale2 ? 1 : 2;
  const a = usePendingAction(`spo2-scale:${next}`);
  if (!s || !s.facts["vitals.spo2"] || s.scores.news2?.applicability === "excluded") return null;
  return <span className="spo2-target" data-scale={scale2 ? 2 : 1}>
    <b>SpO₂ target</b><span className="num">{scale2 ? "88–92%" : "94–98%"}</span>
    <button type="button" role="switch" aria-checked={scale2} aria-label="COPD SpO2 target, 88 to 92 percent"
      className="spo2-switch" disabled={a.disabled} title={a.replay ? "Replay: actions are off" : undefined}
      onClick={() => void api.setSpo2Scale(next)}>
      <span className="spo2-track" aria-hidden><span className="spo2-knob" /></span>
      {a.busy ? "Saving…" : "COPD"}
    </button>
    <ActionNote a={a} />
  </span>;
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
      const missing = r.items.filter((i) => i.state === "missing").map((i) => i.label);
      const toConfirm = r.items.filter((i) => i.state === "pending").length;
      return <span key={r.id} className="sit-ready" data-ready={r.ready || undefined}>
        <b>{r.label}</b>
        <span className="sit-meter" aria-hidden>{r.items.map((i) => <i key={i.key} data-state={i.state} />)}</span>
        <span className="num">{r.done} of {r.total}</span>
        {r.ready ? <em>ready</em> : missing.length ? <em>missing {missing.slice(0, 2).join(", ").toLowerCase()}{missing.length > 2 ? ` +${missing.length - 2}` : ""}</em> : null}
        {!r.ready && toConfirm > 0 && <em className="sit-pending">{toConfirm} to confirm</em>}
      </span>;
    })}
    {lkw && <span className="sit-clock" data-unconfirmed={s.facts["stroke.lkw"]?.status === "unconfirmed" || undefined}><b>LKW</b> {lkw.label.replace(/^LKW\s*/, "")} <span className="num">+{span(clockSeconds(lkw, at, now))}</span>
      {s.facts["stroke.lkw"]?.status === "unconfirmed" && <small>not confirmed</small>}</span>}
    {eta && (() => { const left = clockSeconds(eta, at, now); const tentative = s.facts["transport.eta_min"]?.status === "unconfirmed";
      return <span className="sit-clock" data-unconfirmed={tentative || undefined}><b>ETA</b> <span className="num">{left > 0 ? hhmmss(left).replace(/^00:/, "") : `due ${span(-left)} ago`}</span>
        {tentative && <small>not confirmed</small>}</span>; })()}
    {due && (() => { const left = clockSeconds(due, at, now); return <span className="sit-clock" data-overdue={left <= 0 || undefined}><b>Vitals</b>
      <span className="num">{left > 0 ? `due in ${hhmmss(left).replace(/^00:/, "")}` : "due now"}</span></span>; })()}
  </div>;
}
