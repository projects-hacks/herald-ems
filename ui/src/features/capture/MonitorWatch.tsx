import { useEffect, useRef, useState } from "react";
import { Eye, Pause } from "lucide-react";
import { useHerald } from "@/lib/store";
import { MonitorCapture, monitorIdle, type MonitorRegion, type MonitorStatus } from "./monitor";

export function MonitorWatch({ onStatus }: { onStatus: (status: MonitorStatus) => void }) {
  const patient = useHerald((s) => s.snapshot?.incident.id);
  const blocked = useHerald((s) => s.source !== "live" || s.captureElsewhere);   // a feed blip does not stop the camera; its own socket retries
  const capture = useHerald((s) => s.snapshot?.capture);
  const paused = useHerald((s) => s.ui.capturePaused);
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
    return () => { current.dispose(); session.current = null; };   // watching continues while the tab is in the background
  }, [patient, blocked]);
  useEffect(() => {
    if (capture && !capture.auto && status.active) session.current?.stop("Automatic monitoring was paused.");
  }, [capture?.auto]);
  useEffect(() => {   // continuous: watching starts with the call and follows the pause control in the header
    const s = session.current;
    if (!s || blocked || !patient) return;
    if (paused) { if (status.active || status.starting) s.stop("Paused"); }
    else if (!status.active && !status.starting && !status.error) void s.start(roi).catch(() => {});
  }, [paused, blocked, patient]);
  useEffect(() => {   // a camera stopped by the server or its socket comes back on its own, every 4 s, unless paused
    if (!status.retry || paused || blocked) return;
    const t = window.setTimeout(() => { const s = session.current; if (s && !useHerald.getState().ui.capturePaused) void s.start(roi).catch(() => {}); }, 4000);
    return () => window.clearTimeout(t);
  }, [status.retry, status.message, paused, blocked]);
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
    <p className="capture-help">No video recording. Unselected frames expire from the short memory buffer. Evidence retention follows the vehicle policy. Watching continues while this tab is in the background and reconnects on its own after a dropped link; pausing, changing patient or leaving the page stops it.</p>
  </section>;
}
