import { useEffect, useRef, useState } from "react";
import { Camera, ImagePlus, ZoomIn, ZoomOut } from "lucide-react";
import { useHerald } from "@/lib/store";

export interface CameraStatus { busy: boolean; message: string; failed: boolean }
export function CameraCapture({ visible = true, onStatus }: { visible?: boolean; onStatus?: (status: CameraStatus) => void }) {
  const incident = useHerald((s) => s.snapshot?.incident.id);
  const blocked = useHerald((s) => s.source !== "live" || s.stale || s.conn !== "open");
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
  useEffect(() => { onStatus?.({ busy, message, failed }); }, [busy, message, failed, onStatus]);
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
    stop(); setFile(value); setFailed(false); setMessage("Frozen image · inspect before reading");
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
      setFile(null); setActive(true); setStarting(false);
    } catch (e) { if (token === generation.current) { stop(); setFailed(true); setMessage(e instanceof Error ? e.message : "Camera unavailable"); } }
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
    setBusy(true); setFailed(false); setMessage("Reading photo locally. Extracted facts will need your verification.");
    const abort = new AbortController(); controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 90000);
    try {
      const form = new FormData(); form.append("file", file, "capture.jpg"); form.append("mode", mode); form.append("incident_id", incident);
      const response = await fetch("/api/photo", { method: "POST", body: form, signal: abort.signal });
      if (!response.ok) throw new Error(`Photo reading failed (${response.status}).`);
      const result = await response.json();
      setMessage(`${result.facts.length} proposed facts. Open Review to verify against the original image.`); setFile(null);
    } catch (e) { setFailed(true); setMessage(`${e instanceof Error ? e.message : "Photo reading failed"} Inspect captured notes before retrying; the server may still finish.`); }
    finally { window.clearTimeout(timeout); setBusy(false); }
  };
  return <div className="camera-capture">
    <p>Point at one source. Freeze a clear image, check it, then read it locally. No background video recording.</p>
    <label className="cabin-field">What are you capturing?
      <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={busy}>
        <option value="monitor">Monitor reading</option><option value="pill_bottle">Medication label</option>
        <option value="form">Document / form</option><option value="scene">Scene context</option>
      </select>
    </label>
    <div className="camera-stage" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); select(e.dataTransfer.files[0]); }}>
      <video ref={video} muted playsInline className={active || starting ? "" : "hidden"} />
      {preview && !active && <div className="camera-preview"><img src={preview} alt="Frozen capture for visual verification" style={{ width: `${zoom * 100}%`, maxWidth: "none" }} /></div>}
      {!preview && !active && !starting && <div className="camera-empty"><Camera size={40} /><p>Camera off</p><span>Open camera, choose a photo, or drop an image here</span></div>}
      {active && <span className="camera-label">CAMERA ON · preview only</span>}
    </div>
    <div className="cabin-actions">
      {active ? <><button className="cabin-button primary" onClick={freeze}>Freeze image</button><button className="cabin-button" onClick={stop}>Turn camera off</button></>
        : <button className="cabin-button" onClick={() => void start()} disabled={blocked || starting || busy}><Camera size={20} />{starting ? "Opening camera…" : "Open camera"}</button>}
      {starting && <button className="cabin-button" onClick={stop}>Cancel camera</button>}
      <label className="cabin-button"><ImagePlus size={20} />Choose photo<input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" disabled={blocked || busy} onChange={(e) => { select(e.target.files?.[0]); e.target.value = ""; }} /></label>
      {file && <><button className="cabin-button" aria-label="Zoom photo out" disabled={zoom <= 1} onClick={() => setZoom(Math.max(1, zoom - 0.5))}><ZoomOut size={20} /></button>
        <button className="cabin-button" aria-label="Zoom photo in" disabled={zoom >= 3} onClick={() => setZoom(Math.min(3, zoom + 0.5))}><ZoomIn size={20} /></button>
        <button className="cabin-button primary" disabled={busy || blocked} onClick={() => void read()}>{busy ? "Reading…" : "Read this image"}</button></>}
    </div>
    {message && <p role={failed ? "alert" : "status"} className={failed ? "text-medium-fg" : ""}>{message}</p>}
    <p className="cabin-muted">Medication packaging is evidence of a label—not proof a drug was taken or administered. Photo values are never treated as live monitor readings.</p>
  </div>;
}
