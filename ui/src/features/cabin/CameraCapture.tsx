import { useEffect, useRef, useState } from "react";
import { Camera, ClipboardCheck, ImagePlus, Info, LoaderCircle, ShieldCheck, ZoomIn, ZoomOut } from "lucide-react";
import { useHerald } from "@/lib/store";

export interface CameraStatus { active: boolean; busy: boolean; message: string; failed: boolean }
export function CameraCapture({ visible = true, onStatus, onReview }: { visible?: boolean; onStatus?: (status: CameraStatus) => void; onReview?: () => void }) {
  const incident = useHerald((s) => s.snapshot?.incident.id);
  const blocked = useHerald((s) => s.source !== "live" || s.stale || s.conn !== "open" || !s.snapshot);
  const replay = useHerald((s) => s.source === "fixture");
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [file, setFile] = useState<Blob | null>(null);
  const [preview, setPreview] = useState("");
  const [mode, setMode] = useState("monitor");
  const [zoom, setZoom] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [resultCount, setResultCount] = useState<number | null>(null);
  useEffect(() => { onStatus?.({ active, busy, message, failed }); }, [active, busy, message, failed, onStatus]);
  const stop = () => {
    ++generation.current;
    stream.current?.getTracks().forEach((t) => { t.onended = null; t.stop(); }); stream.current = null;
    setActive(false); setStarting(false);
  };
  useEffect(() => () => { ++generation.current; stream.current?.getTracks().forEach((t) => t.stop()); controller.current?.abort(); }, []);
  useEffect(() => {
    if (blocked) stop();
  }, [blocked]);
  useEffect(() => { if (!visible) stop(); }, [visible]);
  useEffect(() => {
    const hide = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", hide);
    return () => document.removeEventListener("visibilitychange", hide);
  }, []);
  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file); setPreview(url); setZoom(1);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const select = (value?: File) => {
    if (!value || blocked || busy) return;
    if (!/^image\/(jpeg|png|webp)$/.test(value.type) || value.size > 12 * 1024 * 1024) {
      setFailed(true); setMessage("Choose a JPEG, PNG, or WebP image under 12 MB."); return;
    }
    stop(); setFile(value); setResultCount(null); setFailed(false); setMessage("Frozen image · inspect before reading");
  };
  const start = async () => {
    if (blocked || starting || busy) return;
    const token = ++generation.current; setStarting(true); setFailed(false); setMessage("");
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Live camera needs HTTPS or localhost. Choose a photo instead.");
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (token !== generation.current) { media.getTracks().forEach((t) => t.stop()); return; }
      stream.current = media;
      media.getTracks().forEach((t) => { t.onended = () => { stop(); setFailed(true); setMessage("Camera disconnected. Choose a photo or reopen the camera."); }; });
      if (video.current) { video.current.srcObject = media; await video.current.play(); }
      if (token !== generation.current) return;
      setFile(null); setResultCount(null); setActive(true); setStarting(false);
    } catch (e) { if (token === generation.current) { stop(); setFailed(true); setMessage(e instanceof Error && e.name === "NotAllowedError" ? "Camera access is blocked. Allow camera access in your browser settings, then try again, or choose a photo." : e instanceof Error ? e.message : "Camera unavailable. Choose a photo or try again."); } }
  };
  const freeze = () => {
    const v = video.current; if (!v?.videoWidth || !v.videoHeight) return;
    const token = generation.current;
    const canvas = document.createElement("canvas"); canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    canvas.getContext("2d")?.drawImage(v, 0, 0);
    canvas.toBlob((blob) => { if (blob && token === generation.current) { setFile(blob); stop(); setMessage("Frozen image · inspect before reading"); } }, "image/jpeg", 0.9);
  };
  const read = async () => {
    if (!file || busy || blocked || !incident) return;
    setBusy(true); setFailed(false); setResultCount(null); setMessage("Reading photo locally. Extracted facts will need your verification.");
    const abort = new AbortController(); controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 90000);
    try {
      const form = new FormData(); form.append("file", file, "capture.jpg"); form.append("mode", mode); form.append("incident_id", incident);
      const response = await fetch("/api/photo", { method: "POST", body: form, signal: abort.signal });
      if (!response.ok) throw new Error(`Photo reading failed (${response.status}).`);
      const result = await response.json();
      setResultCount(result.facts.length);
      if (result.facts.length) { setMessage(`${result.facts.length} proposed readings ready. Verify each against the image before using it.`); setFile(null); }
      else setMessage("No readable information found. Try a clearer photo or a different image type.");
    } catch (e) { setFailed(true); setMessage(`${e instanceof Error ? e.message : "Photo reading failed"} Inspect captured notes before retrying; the server may still finish.`); }
    finally { window.clearTimeout(timeout); setBusy(false); }
  };
  const choosePhoto = <label className="cabin-button"><ImagePlus size={18} aria-hidden />Choose photo<input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" disabled={blocked || busy} onChange={(e) => { select(e.target.files?.[0]); e.target.value = ""; }} /></label>;
  const openCamera = <button className="cabin-button primary" onClick={() => void start()} disabled={blocked || starting || busy}><Camera size={18} aria-hidden />Open camera</button>;
  return <div className="camera-capture">
    <div className="capture-source-row">
      <label className="cabin-field">Image type
        <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={busy}>
          <option value="monitor">Monitor reading</option><option value="pill_bottle">Medication label</option>
          <option value="form">Document / form</option><option value="scene">Scene context</option>
        </select>
      </label>
      <span className="capture-source-status"><Camera size={16} aria-hidden />This device · {active ? "preview on" : starting ? "opening camera" : "camera off"}</span>
    </div>
    {blocked && <p className="capture-notice">{replay ? "Photo capture is unavailable in this recorded demo. Connect to the vehicle to capture an image." : "Connect to the vehicle to capture and read an image."}</p>}
    <div className="camera-stage" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); select(e.dataTransfer.files[0]); }}>
      <video ref={video} muted playsInline className={active ? "" : "hidden"} />
      {preview && !active && !starting && <div className="camera-preview"><img src={preview} alt="Frozen capture for visual verification" style={{ width: `${zoom * 100}%`, maxWidth: "none" }} /></div>}
      {starting && <div className="camera-empty" role="status"><LoaderCircle size={32} className="motion-safe:animate-spin" aria-hidden /><h2>Opening camera</h2><p>Allow camera access when your browser asks.</p><button className="cabin-button" onClick={stop}>Cancel camera</button></div>}
      {!preview && !active && !starting && <div className="camera-empty">
        {resultCount ? <ClipboardCheck size={32} aria-hidden /> : <Camera size={32} aria-hidden />}
        <h2>{resultCount ? "Ready for your review" : "Capture a clear image"}</h2>
        <p>{resultCount ? `${resultCount} proposed readings need your verification.` : "Use this device’s camera or choose a photo. You can also drop an image here."}</p>
        <div className="cabin-actions">{resultCount && onReview ? <button className="cabin-button primary" onClick={onReview}><ClipboardCheck size={18} aria-hidden />Review readings</button> : openCamera}{choosePhoto}</div>
        {!!resultCount && <button className="cabin-button" disabled={blocked || busy} onClick={() => void start()}>Take another photo</button>}
      </div>}
      {active && <span className="camera-label">Preview only · tap Capture photo when ready</span>}
    </div>
    {(active || file) && !starting && <div className="cabin-actions camera-action-bar">
      <div>{active ? <button className="cabin-button" onClick={stop}>Turn camera off</button> : <>{openCamera}{choosePhoto}</>}</div>
      <div>{active ? <button className="cabin-button primary" onClick={freeze}><Camera size={18} aria-hidden />Capture photo</button> : <>
        <button className="cabin-button" aria-label="Zoom photo out" disabled={zoom <= 1} onClick={() => setZoom(Math.max(1, zoom - 0.5))}><ZoomOut size={18} /></button>
        <button className="cabin-button" aria-label="Zoom photo in" disabled={zoom >= 3} onClick={() => setZoom(Math.min(3, zoom + 0.5))}><ZoomIn size={18} /></button>
        <button className="cabin-button primary" disabled={busy || blocked} onClick={() => void read()}>{busy ? <LoaderCircle size={18} className="motion-safe:animate-spin" aria-hidden /> : <ClipboardCheck size={18} aria-hidden />}{busy ? "Reading photo…" : "Read photo"}</button>
      </>}</div>
    </div>}
    {message && <p role={failed ? "alert" : "status"} className="capture-notice">{message}</p>}
    <p className="capture-help"><ShieldCheck size={16} aria-hidden />Only the photo you submit is read. Proposed information needs your verification.</p>
    {mode === "pill_bottle" && <p className="capture-help"><Info size={16} aria-hidden />A medication label does not confirm that a drug was taken or administered.</p>}
  </div>;
}
