import { useEffect, useRef, useState } from "react";
import { Eye, Pause } from "lucide-react";
import { useHerald } from "@/lib/store";
import { MonitorCapture, monitorIdle, type MonitorRegion, type MonitorStatus } from "./monitor";

export function MonitorWatch({ onStatus }: { onStatus: (status: MonitorStatus) => void }) {
  const patient = useHerald((s) => s.snapshot?.incident.id);
  const blocked = useHerald((s) => s.source !== "live" || s.stale || s.conn !== "open");
  const capture = useHerald((s) => s.snapshot?.capture);
  const video = useRef<HTMLVideoElement>(null);
  const session = useRef<MonitorCapture | null>(null);
  const changed = useRef(onStatus); changed.current = onStatus;
  const [status, setStatus] = useState(monitorIdle);
  const [roi, setRoi] = useState<MonitorRegion>({ x0: 0, y0: 0, x1: 1, y1: 1 });
  const [error, setError] = useState("");
  useEffect(() => { setRoi({ x0: 0, y0: 0, x1: 1, y1: 1 }); setError(""); }, [patient]);
  useEffect(() => {
    setStatus(monitorIdle); changed.current(monitorIdle);
    if (!patient || blocked || !video.current) return;
    const current = new MonitorCapture(video.current, patient, (next) => { setStatus(next); changed.current(next); });
    session.current = current;
    const hidden = () => { if (document.hidden) current.stop("Camera paused because this browser tab is hidden."); };
    document.addEventListener("visibilitychange", hidden);
    return () => { document.removeEventListener("visibilitychange", hidden); current.dispose(); session.current = null; };
  }, [patient, blocked]);
  useEffect(() => {
    if (capture && !capture.auto && status.active) session.current?.stop("Automatic monitoring was paused.");
  }, [capture?.auto]);
  return <section className="monitor-watch" aria-label="Continuous monitor watch">
    <h2>Watch the monitor through the journey</h2>
    <p>Aim at the equipment. After one start, this camera keeps sending frames while you use other care pages. The vehicle selects usable stills, reads changes, and holds proposed readings for review.</p>
    <div className="monitor-viewfinder">
      <video ref={video} muted playsInline aria-label="Continuous monitor camera preview" />
      {!status.active && !status.starting && <span>Camera starts only when you choose Start monitor watch</span>}
      {status.active && capture?.roi && <div className="monitor-region" style={{ left: `${capture.roi.x0 * 100}%`, top: `${capture.roi.y0 * 100}%`, width: `${(capture.roi.x1 - capture.roi.x0) * 100}%`, height: `${(capture.roi.y1 - capture.roi.y0) * 100}%` }} />}
    </div>
    <form onSubmit={(event) => { event.preventDefault(); setError(""); void session.current?.region(roi).catch((e) => setError(e.message)); }}>
      <fieldset disabled={blocked || status.starting}><legend>Monitor area · percentages of the camera image</legend>
        {([['x0', 'Left'], ['y0', 'Top'], ['x1', 'Right'], ['y1', 'Bottom']] as const).map(([key, label]) => <label key={key}>{label}<input type="number" min="0" max="100" value={Math.round(roi[key] * 100)} onChange={(event) => setRoi({ ...roi, [key]: Number(event.target.value) / 100 })} /></label>)}
        <button className="cabin-button" disabled={!status.active}>Apply monitor area</button>
      </fieldset>
    </form>
    <div className="cabin-actions">
      <button className={`cabin-button ${status.active || status.starting ? "recording" : "primary"}`} disabled={blocked || !patient} onClick={() => status.active || status.starting ? session.current?.stop() : void session.current?.start(roi)}>
        {status.active || status.starting ? <Pause size={20} /> : <Eye size={20} />}{status.active || status.starting ? "Stop monitor watch" : "Start monitor watch"}
      </button>
      <span role={status.error ? "alert" : "status"}>{blocked ? "Connect to the live vehicle to start monitoring." : status.message}</span>
    </div>
    {error && <p role="alert">{error}</p>}
    <p className="capture-help">No video recording. Unselected frames expire from the short memory buffer. Evidence retention follows the vehicle policy. Hiding this browser tab, changing patient or losing the connection stops capture.</p>
    {capture?.last && <p className="capture-notice">Latest camera decision: {capture.last.reason}</p>}
  </section>;
}
