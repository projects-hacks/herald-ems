// The browser owns camera permission; the vehicle server owns capture policy. No model runs here.
const $ = (id) => document.getElementById(id);
const video = $("camera-preview");
let media = null, socket = null, timer = null, generation = 0, owner = null, busy = false, status = null;
const error = (message) => { $("capture-error").textContent = message; };
async function request(path, body, method = "POST") {
  if (owner && method === "POST") body = { ...body, incident_id: owner };
  if (owner && method === "DELETE") path += `?incident_id=${encodeURIComponent(owner)}`;
  const response = await fetch(path, { method, ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`Herald did not accept the request (${response.status})`);
  return response.json();
}
function closeDevices() {
  generation++; clearTimeout(timer); timer = null;
  media?.getTracks().forEach((track) => { track.onended = null; track.stop(); }); media = null;
  if (socket) { socket.onclose = null; socket.close(); socket = null; }
  video.srcObject = null; $("start-camera").disabled = false; $("stop-camera").disabled = true;
}
async function stop() {
  closeDevices();
  try { status = await request("/api/capture/auto", { on: false }); render(); }
  catch (e) { error(`${e.message}. Camera is off locally.`); }
}
function render() {
  if (!status) return;
  $("capture-state").textContent = `Herald sees: ${status.sees}${status.auto && status.sees === "off" ? " · waiting for camera frames" : ""} · ${status.counts.captured} reads · ${status.counts.stored} evidence images`;
  if (status.error) error(status.error);
  const box = $("roi-box"), roi = status.roi;
  box.hidden = !roi || !media;
  if (roi) { box.style.left = `${roi.x0 * 100}%`; box.style.top = `${roi.y0 * 100}%`; box.style.width = `${(roi.x1 - roi.x0) * 100}%`; box.style.height = `${(roi.y1 - roi.y0) * 100}%`; }
}
async function connect(token) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/frames`);
  socket = ws;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { ws.close(); reject(new Error("Camera connection timed out")); }, 5000);
    ws.onopen = () => { clearTimeout(timeout); resolve(); };
    ws.onerror = () => { clearTimeout(timeout); reject(new Error("Camera connection failed")); };
    ws.onclose = () => { clearTimeout(timeout); reject(new Error("Camera connection refused; check whether another camera is open")); };
  });
  if (token !== generation) { ws.close(); return; }
  ws.onmessage = (event) => {
    const reply = JSON.parse(event.data);
    if (reply.error) error(reply.error);
  };
  ws.onclose = () => { closeDevices(); error("Camera connection closed. Capture stopped; start explicitly to reconnect."); };
}
async function sendFrame(token) {
  if (token !== generation || !media || socket?.readyState !== WebSocket.OPEN || !video.videoWidth) return;
  if (socket.bufferedAmount > 1024 * 1024) { error("Camera link is behind; skipping frames."); return; }
  const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight));
  const canvas = document.createElement("canvas"); canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", .8));
  if (token === generation && blob && blob.size <= 1024 * 1024 && socket?.readyState === WebSocket.OPEN) socket.send(blob);
}
async function start(manual = false) {
  if (busy) return;
  busy = true; error(""); closeDevices(); const token = generation;
  $("start-camera").disabled = true; $("stop-camera").disabled = false;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Continuous camera needs HTTPS or localhost. Use the one-shot photo controls below.");
    status = await request("/api/capture/status", undefined, "GET"); owner = status.incident_id;
    if (token !== generation) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "environment" } } });
    if (token !== generation) { stream.getTracks().forEach((t) => t.stop()); return; }
    media = stream; video.srcObject = stream;
    media.getTracks().forEach((t) => { t.onended = () => { void stop(); error("Camera disconnected."); }; });
    await video.play(); await connect(token);
    if (token !== generation) return;
    if (manual) {
      const mode = $("show-mode").value;
      await request("/api/capture/now", mode ? { mode } : {});
      await sendFrame(token);
      // Keep the socket until the server receives the selected still; stop tracks immediately.
      media.getTracks().forEach((t) => t.stop()); media = null;
      timer = setTimeout(closeDevices, 1500);
    } else {
      status = await request("/api/capture/auto", { on: true });
      const tick = async () => {
        if (token !== generation) return;
        try { await sendFrame(token); } catch (e) { closeDevices(); error(e.message); return; }
        if (token === generation) timer = setTimeout(tick, 1000 / status.fps_in);
      };
      await tick();
    }
    render();
  } catch (e) { if (token === generation) { closeDevices(); error(e.message); } }
  finally { busy = false; }
}
$("start-camera").onclick = () => void start();
$("stop-camera").onclick = () => void stop();
$("show-herald").onclick = async () => {
  if (!media) { await start(true); return; }
  try { const mode = $("show-mode").value; await request("/api/capture/now", mode ? { mode } : {}); }
  catch (e) { error(e.message); }
};
async function saveROI(roi) {
  status = await request("/api/capture/roi", { ...roi, target: "monitor" }); render();
  for (const key of ["x0", "y0", "x1", "y1"]) $("roi-" + key).value = Math.round(roi[key] * 100);
}
$("roi-form").onsubmit = async (e) => {
  e.preventDefault();
  try { await saveROI(Object.fromEntries(["x0", "y0", "x1", "y1"].map((k) => [k, Number($("roi-" + k).value) / 100]))); error(""); }
  catch (err) { error(err.message); }
};
$("clear-roi").onclick = async () => { try { status = await request("/api/capture/roi", undefined, "DELETE"); render(); } catch (e) { error(e.message); } };
let anchor = null;
function position(e) { const r = video.getBoundingClientRect(); return [Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)), Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))]; }
video.onpointerdown = (e) => { if (media) { anchor = position(e); video.setPointerCapture(e.pointerId); } };
video.onpointercancel = () => { anchor = null; };
video.onpointerup = async (e) => {
  if (!anchor) return;
  const end = position(e), start = anchor; anchor = null;
  try { await saveROI({ x0: Math.min(start[0], end[0]), y0: Math.min(start[1], end[1]), x1: Math.max(start[0], end[0]), y1: Math.max(start[1], end[1]) }); }
  catch (err) { error(err.message); }
};
setInterval(async () => {
  if (document.hidden) return;
  try {
    const next = await request("/api/capture/status", undefined, "GET");
    if (media && (next.incident_id !== owner || (!next.auto && !busy))) { closeDevices(); error("Capture stopped or patient changed. Start again explicitly."); }
    status = next; render();
  } catch { if (media) { closeDevices(); error("Server disconnected. Camera stopped."); } }
}, 1000);
document.addEventListener("visibilitychange", () => { if (document.hidden) void stop(); });
window.addEventListener("pagehide", closeDevices);
