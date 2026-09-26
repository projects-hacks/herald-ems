// Herald, live: the copilot's presence on the screen. The orb is its voice (it moves with the cabin's sound and is
// the one pause/resume control), the caption is the last thing it heard with the values it took from those words
// marked, and the chips are what it recorded and what that changed. The eye shows what the camera is looking at.
// Everything here is something Herald did; nothing is a model internal.
import { useEffect, useRef } from "react";
import { Eye, EyeOff, TriangleAlert } from "lucide-react";
import { activity, liveHeard, type Presence } from "@/lib/copilot";
import { hhmm } from "@/lib/format";
import { useHerald } from "@/lib/store";
import type { MonitorStatus } from "@/features/capture/monitor";

type OrbState = "listening" | "thinking" | "paused" | "down" | "waiting" | "replay";

export function HeraldLive({ p, paused, disabled, onToggle, level, waitingTap, warning, monitor }: {
  p: Presence; paused: boolean; disabled?: boolean; onToggle: () => void; level: number; waitingTap: boolean;
  warning?: string | null; monitor: MonitorStatus;
}) {
  const s = useHerald((st) => st.snapshot);
  const heard = s ? liveHeard(s) : null;
  const state: OrbState = p.tone === "replay" ? "replay" : p.tone === "down" ? "down" : paused ? "paused"
    : waitingTap ? "waiting" : heard?.working ? "thinking" : p.tone === "ok" ? "listening" : "paused";
  const status = state === "down" ? p.text : state === "paused" ? "Paused. Tap to listen and watch"
    : state === "waiting" ? "Tap anywhere to start listening" : state === "thinking" ? "Understanding what was just said…"
    : state === "replay" ? p.text : p.text;
  const warn = !!warning && state !== "down" && state !== "paused" && state !== "replay";   // still listening, but the medic should know
  return <section className="herald-live" data-state={state} data-warn={warn || undefined} aria-label="Herald">
    <button type="button" className="live-orb" style={{ "--level": state === "listening" ? level.toFixed(2) : "0" } as React.CSSProperties}
      disabled={disabled} onClick={onToggle} aria-label={state === "listening" || state === "thinking" ? "Pause listening and watching" : "Listen and watch"}>
      <span className="orb-halo" aria-hidden /><span className="orb-core" aria-hidden>{state === "down" && <TriangleAlert size={22} />}</span>
    </button>
    <div className="live-body">
      <p className="live-status"><b>Herald</b><span role={state === "down" ? "alert" : "status"}>{status}</span>
        {warn && <em className="live-warning" role="status">{warning}</em>}</p>
      {heard ? <figure className="live-heard" key={heard.id}>
        <blockquote>“{heard.segments.map((g, i) => g.hl ? <mark key={i}>{g.t}</mark> : <span key={i}>{g.t}</span>)}”</blockquote>
        <figcaption>{heard.who ?? "Heard"} · <span className="num">{hhmm(heard.ts)}</span></figcaption>
      </figure> : <p className="live-hint">Listening to the crew, the patient and family. Ask out loud: “show me the protocol for …”</p>}
      {heard && (heard.working ? <ul className="live-chips" aria-label="Understanding"><li className="chip-skeleton" /><li className="chip-skeleton" /></ul>
        : heard.chips.length + heard.effects.length > 0 && <ul className="live-chips" aria-label="What Herald recorded">
          {heard.chips.map((c, i) => <li key={c.id} data-status={c.status} style={{ animationDelay: `${i * 70}ms` }}>
            <span>{c.label}</span><b>{c.value}</b>{c.status === "unconfirmed" && <small>to confirm</small>}</li>)}
          {heard.effects.map((e, i) => <li key={e} className="chip-effect" style={{ animationDelay: `${(heard.chips.length + i) * 70}ms` }}>{e}</li>)}
        </ul>)}
    </div>
    <LiveEye monitor={monitor} paused={paused} />
  </section>;
}

/** What the camera sees, and the last thing Herald read from it. The camera runs with the call and has no controls of
 * its own: it follows the pause in the header and reconnects by itself. */
function LiveEye({ monitor, paused }: { monitor: MonitorStatus; paused: boolean }) {
  const s = useHerald((st) => st.snapshot);
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = video.current; if (!v) return;
    v.srcObject = monitor.stream ?? null;
    if (monitor.stream) void v.play().catch(() => {});
  }, [monitor.stream]);
  const read = s ? activity(s, 20).find((l) => l.kind === "read" || l.kind === "checked") : undefined;
  const on = monitor.active && !!monitor.stream;
  const failed = monitor.error && !on;
  return <div className="live-eye" data-on={on || undefined} data-failed={failed || undefined} role="group" aria-label="Camera">
    <span className="eye-view">
      <video ref={video} muted playsInline aria-hidden />
      {on ? <span className="eye-scan" aria-hidden /> : <EyeOff size={22} aria-hidden />}
    </span>
    <span className="eye-text">
      <b>{on ? <><Eye size={14} aria-hidden /> Watching the monitor</> : failed && monitor.retry && !paused ? "Camera reconnecting…" : failed ? "Camera stopped" : paused ? "Camera paused" : monitor.starting ? "Starting the camera…" : "Camera off"}</b>
      <span>{failed ? (monitor.retry && !paused ? "Comes back on its own" : monitor.message) : read ? read.text.replace(/^Read the monitor — /, "") : on ? "Waiting for a clear frame" : paused ? "Resumes when you listen again" : "Starts with the call"}</span>
    </span>
  </div>;
}
