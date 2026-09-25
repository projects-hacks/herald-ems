import { useState } from "react";
import { Camera, ExternalLink, Eye, EyeOff, Info } from "lucide-react";
import { useHerald } from "@/lib/store";
import { captureAction } from "./actions";

export function CaptureControl({ compact = false, stopOnly = false, onSetup }: { compact?: boolean; stopOnly?: boolean; onSetup?: () => void }) {
  const capture = useHerald((s) => s.snapshot?.capture);
  const disabled = useHerald((s) => s.source === "fixture" || s.stale || s.conn !== "open");
  const replay = useHerald((s) => s.source === "fixture");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("");
  async function run(path: string, body: Record<string, unknown>) {
    if (busy || disabled) return;
    setBusy(true); setError("");
    try { await captureAction(path, body); } catch (e) { setError(e instanceof Error ? e.message : "Capture request failed"); }
    finally { setBusy(false); }
  }
  const watching = capture?.sees === "watching", reading = capture?.sees === "reading";
  if (stopOnly) return <div><button className="cabin-button" disabled={disabled || busy} onClick={() => void run("/api/capture/auto", { on: false })}><EyeOff size={18} />{busy ? "Stopping…" : "Stop auto capture"}</button>{error && <p role="alert">{error}</p>}</div>;
  if (compact) return <section className="capture-compact" aria-label="Camera capture">
    <span role="status">Selected stills need verification</span>
    <button className="cabin-button" disabled={disabled || busy || !capture} onClick={() => void run("/api/capture/now", {})}><Camera size={18} />{busy ? "Requesting…" : "Capture once"}</button>
    <button className="cabin-button" onClick={onSetup}>Camera options</button>
    {(error || capture?.error) && <p role="alert">{error || capture?.error}</p>}
  </section>;
  return <section className="connected-camera" aria-label="Connected camera controls">
    <div className="connected-camera-status">
      {watching || reading ? <Eye size={24} aria-hidden /> : <EyeOff size={24} aria-hidden />}
      <div><strong role="status">{disabled ? replay ? "Recorded camera state" : "Camera connection unavailable" : !capture ? "Camera status unavailable" : reading ? "Reading a captured image" : watching ? "Camera watching" : "Camera off"}</strong>
        <p>{capture?.auto && capture.sees === "off" ? "Automatic capture is enabled. Waiting for a camera feed." : "Control a camera connected to this vehicle."}</p></div>
    </div>
    <div className="connected-camera-setup">
      <div><h2>Connect a camera source</h2><p>Open setup on the camera device to start its feed and select the monitor area. Keep that page visible while capturing.</p></div>
      {disabled ? <button className="cabin-button" disabled>Open camera setup<ExternalLink size={17} aria-hidden /></button> : <a className="cabin-button" href="/classic/capture.html" target="_blank" rel="noreferrer">Open camera setup<ExternalLink size={17} aria-hidden /></a>}
    </div>
    {disabled && <p className="capture-notice">{replay ? "Camera controls are unavailable in a recorded demo." : "Reconnect to the vehicle to control its camera."}</p>}
    <div className="connected-camera-controls">
      <label>Image type<select value={mode} disabled={busy || disabled} onChange={(e) => setMode(e.target.value)}>
        <option value="">Detect automatically</option><option value="monitor">Monitor reading</option><option value="pill_bottle">Medication label</option><option value="form">Document / form</option><option value="scene">Scene context</option>
      </select></label>
      <button type="button" className="cabin-button" aria-pressed={capture?.auto ?? false} disabled={disabled || busy || !capture}
        onClick={() => void run("/api/capture/auto", { on: !capture?.auto })}>{capture?.auto ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}{capture?.auto ? "Pause auto capture" : "Enable auto capture"}</button>
      <button type="button" className="cabin-button primary" disabled={disabled || busy || !capture}
        onClick={() => void run("/api/capture/now", mode ? { mode } : {})}><Camera size={18} aria-hidden />{busy ? "Requesting…" : "Capture once"}</button>
    </div>
    <p className="capture-help"><Info size={16} aria-hidden /><span>{capture?.roi ? "Monitor area selected. " : "Select a monitor area in setup to watch for changes. "}Every captured reading needs verification.{capture?.pending ? ` ${capture.pending} capture(s) waiting.` : ""}</span></p>
    {(error || capture?.error) && <p role="alert" className="capture-notice">{error || capture?.error}</p>}
  </section>;
}
