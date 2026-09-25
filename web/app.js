// Herald NOW screen. Renders the live patient state pushed over /ws.
let S = null;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const fmtVal = (v) => Array.isArray(v) ? (v.length ? v.join(", ") : "none reported") : (v === true ? "yes" : v === false ? "no" : v);

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.type === "state") { S = m.state; render(); } };
  ws.onclose = () => setTimeout(connect, 1000);
}

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function srcTag(f) {
  const who = f.speaker ? f.speaker : f.role;
  const how = f.provenance?.photo_id ? `<a href="/api/photo/${f.provenance.photo_id}" target="_blank">📷</a>` : f.provenance?.audio_id ? "🎙" : f.captured_by === "device" ? "📟" : "⌨";
  return `${how} ${esc(who)} · ${hhmm(f.ts)}`;
}

function play(audioId) { const p = $("player"); p.src = `/api/audio/${audioId}`; p.play(); }
async function act(id, action) { await api(`/api/facts/${id}/${action}`, { method: "POST" }); }

function render() {
  if (!S) return;
  $("dispatch").textContent = `dispatch: ${S.incident.dispatch || "—"}`;
  $("cloud").textContent = `cloud AI calls ${S.counters.cloud_ai_calls}`;
  $("summary").textContent = S.summary || "Waiting for the call…";

  // readiness (gap-first)
  $("readiness").innerHTML = S.readiness.map((r) => `
    <div class="alert-box ${r.ready ? "ready" : ""}">
      <div class="alert-head">${esc(r.label.toUpperCase())}
        <span class="bar">${r.items.map((i) => `<i class="${i.state === "done" ? "on" : i.state === "pending" ? "pend" : ""}"></i>`).join("")}</span>
        <span>${r.done} of ${r.total} ready${r.ready ? " ✓" : ""}</span></div>
      <div class="items">${r.items.map((i) => `<span class="chip ${i.state}">${i.state === "done" ? "✓" : i.state === "pending" ? "…" : "○"} ${esc(i.label)}</span>`).join("")}</div>
    </div>`).join("") || `<div class="muted">No pre-alert type active</div>`;

  // needs attention
  const na = S.needs_attention;
  const needRow = (x) => `<div class="need ${x.pending_confirm ? "pend" : ""}"><span class="dot"></span>${esc(x.label)}${x.pending_confirm ? ' <span class="src">(awaiting confirm)</span>' : ""}</div>`;
  $("missing").innerHTML =
    (na.missing.length ? `<div class="sub">Not yet captured</div>${na.missing.map(needRow).join("")}` : "") +
    (na.unknown.length ? `<div class="sub">Not yet asked</div>${na.unknown.map(needRow).join("")}` : "") ||
    `<div class="muted">Nothing missing</div>`;

  // changed
  $("changed").innerHTML = S.changed.length ? S.changed.map((c) =>
    `<div class="row"><span class="k">${esc(c.label)}</span><span class="v trend ${c.significant ? "sig" : ""}">${c.direction === "up" ? "↑" : c.direction === "down" ? "↓" : "→"} ${c.series.join(" → ")}</span></div>`).join("")
    : `<span class="muted">No changes yet</span>`;

  // scores
  const n = S.scores.news2, rc = S.scores.race, ft = S.scores.field_triage;
  const hist = S.scores.news2_history.filter((h) => h.complete).map((h) => h.score);
  const parts = (p) => Object.entries(p).map(([k, v]) => `${esc(k)} ${esc(fmtVal(v.value))} (+${v.points})`).join(" · ");
  $("scores").innerHTML = `
    <div class="score"><span class="big band-${n.band}">NEWS2 ${n.complete ? n.score : "—"}</span>
      ${hist.length > 1 ? `<span class="trend"> ${hist.join(" → ")}</span>` : ""}
      <span class="band-${n.band}"> ${esc(n.band)}</span>
      <div class="parts">${parts(n.parts)}${n.missing.length ? ` · <b>missing:</b> ${esc(n.missing.join(", "))}` : ""}</div>
      <div class="parts">${esc(n.thresholds)} · ${esc(n.source)}</div></div>
    <div class="score"><span class="big ${rc.positive ? "band-high" : ""}">RACE ${rc.complete ? rc.score : "—"}</span>
      ${rc.complete ? `<span> ${rc.positive ? "≥5: large-vessel screen positive" : "&lt;5: screen negative"}</span>` : ""}
      <div class="parts">${parts(rc.parts)}${rc.missing.length ? ` · <b>missing:</b> ${esc(rc.missing.join(", "))}` : ""}</div>
      <div class="parts">${esc(rc.evidence)} · ${esc(rc.source)}</div></div>
    ${(ft.red.length || ft.yellow.length) ? `<div class="score"><b>${esc(ft.name)}</b>
      ${ft.red.map((x) => `<div class="band-high">RED: ${esc(x)}</div>`).join("")}
      ${ft.yellow.map((x) => `<div class="band-medium">YELLOW: ${esc(x)}</div>`).join("")}
      <div class="parts">${esc(ft.source)}</div></div>` : ""}`;

  // alerts
  const high = a => (a.type === "trauma_alert_criteria" && a.level === "red") || (a.type === "news2_rise" && a.band === "high");
  $("alerts").innerHTML = S.alerts.length ? [...S.alerts].sort((a, b) => Number(high(b)) - Number(high(a))).map((a) => {
    if (a.type === "trauma_alert_criteria" || a.type === "sepsis_prenotification") return `<div class="alert ${a.level === "red" ? "band-high" : "warn"}"><b>${a.level === "red" ? "HIGH" : "CHECK"} · ${esc(a.label)}</b>${a.criteria.map(line => `<p>${esc(line)}</p>`).join("")}${(a.county_rule || []).map(line => `<p>${esc(a.county || "")} · ${esc(line)}</p>`).join("")}</div>`;
    if (a.type === "contradiction") return `<div class="alert">⚠ <b>${esc(a.label)}: sources disagree</b><br>${a.facts.map((f) =>
      `${esc(f.speaker || f.role)}: <b>${esc(fmtVal(f.value))}</b> <span class="src">(${hhmm(f.ts)})</span>${f.provenance?.audio_id ? ` <button onclick="play('${f.provenance.audio_id}')">▶</button>` : ""}`).join("<br>")}
      <br><button onclick="act('${a.confirm_fact_id}','confirm')">Confirm latest</button><button onclick="act('${a.confirm_fact_id}','reject')">Reject latest</button></div>`;
    if (a.type === "news2_rise") return `<div class="alert warn">▲ <b>NEWS2 ${a.from} → ${a.to}</b> (${esc(a.band)} band). No single vital needed to look alarming.</div>`;
    if (a.type === "race_positive") return `<div class="alert warn">RACE ${a.score} (≥5): large-vessel screen positive. See county destination policy.</div>`;
    if (a.type === "significant_change") return `<div class="alert warn">${esc(a.label)} changed: ${a.series.join(" → ")}</div>`;
    if (a.type === "confirm_required") return `<div class="alert">${esc(a.label)} requires confirmation: <b>${esc(fmtVal(a.facts[0].value))}</b><button onclick="act('${a.confirm_fact_id}','confirm')">Confirm</button><button onclick="act('${a.confirm_fact_id}','reject')">Reject</button></div>`;
    return "";
  }).join("") : `<span class="muted">None</span>`;

  renderClocks();
  renderRelay();

  // facts
  const facts = Object.values(S.facts);
  $("facts").innerHTML = facts.length ? facts.map((f) => `
    <div class="row fact"><span class="k">${esc(f.label)}</span>
      <span class="v ${f.status === "unconfirmed" ? "unconf" : ""}">${esc(fmtVal(f.value))}${f.unit ? " " + esc(f.unit) : ""}
        <span class="src">${srcTag(f)}</span>
        ${f.provenance?.audio_id ? `<button onclick="play('${f.provenance.audio_id}')">▶</button>` : ""}
        ${f.status === "unconfirmed" ? `<button onclick="act('${f.id}','confirm')">✓</button><button onclick="act('${f.id}','reject')">✕</button>` : ""}
      </span></div>`).join("") : `<span class="muted">Nothing captured yet</span>`;

  $("log").innerHTML = [...S.transcripts].reverse().map((t) =>
    `<div>${hhmm(t.ts)} <b>${esc(t.speaker || t.captured_by)}</b>: “${esc(t.text)}” <span class="src">→ ${t.fact_ids.length} facts · rules ${t.extract.rules} · llm ${t.extract.llm ?? "off"} · ${t.extract.ms} ms</span></div>`).join("");
}

const ER_LABELS = { "alert.readiness": "Pre-alert", "code_status": "Code status", "meds.anticoagulant": "Anticoagulant",
  "allergies": "Allergies", "stroke.lkw": "Last known well", "complaint.chief": "Chief complaint", "score.news2": "NEWS2",
  "score.race": "RACE", "vitals.sbp": "SBP", "vitals.dbp": "DBP", "vitals.hr": "HR", "vitals.spo2": "SpO2", "vitals.rr": "RR",
  "vitals.glucose": "Glucose", "vitals.consciousness": "ACVPU", "stroke.deficits": "Deficits", "transport.eta_min": "ETA",
  "transport.destination": "Destination", "patient.age": "Age", "patient.sex": "Sex", "stroke.onset_witnessed": "Onset witnessed",
  "vitals.temp": "Temp", "vitals.on_oxygen": "Oxygen", "meds.list": "Medications", "scene.notes": "Scene notes" };
function renderRelay() {
  const r = S.relay; if (!r) return;
  const net = $("net");
  const label = { good: "ED link: good", weak: "ED link: weak", down: "ED link: OFFLINE", unknown: "ED link: …", "not configured": "ED link: not configured" }[r.link] || r.link;
  net.textContent = label + (S.netem ? ` (emulated: ${S.netem})` : "");
  net.className = "pill " + (r.link === "good" ? "ok" : r.link === "down" || r.link === "weak" ? "bad" : "dim");
  if (!r.authorized) {
    $("er").innerHTML = r.configured
      ? `<button onclick="authorize()">Authorize pre-alert → <b>${esc(S.facts["transport.destination"]?.value || "destination")}</b></button> <span class="src">once; in-scope updates then flow on their own</span>`
      : `<span class="muted">ED link not configured (set HERALD_ED_URL)</span>`;
    return;
  }
  const rows = Object.entries(r.sync).map(([k, st]) => `<div class="row"><span class="k">${esc(ER_LABELS[k] || k)}</span><span class="v">${st === "sent" ? "✓ sent" : "⏳ queued"}</span></div>`).join("");
  const log = [...r.log].reverse().slice(0, 5).map((e) => `<div class="src">#${e.seq} ${e.tier} · ${e.bytes} B · ${e.result}${e.rtt_ms != null ? " · " + e.rtt_ms + " ms" : ""}${e.queued_after ? " · " + e.queued_after + " still queued" : ""}<br>${esc(e.keys.slice(0, 6).join(", "))}${e.keys.length > 6 ? "…" : ""}</div>`).join("");
  $("er").innerHTML = `<div class="src">→ ${esc(r.authorized.destination)} · scope: ${esc(r.authorized.scope)}</div>${rows}
    <div class="sub">Link</div><div class="row"><span class="k">Sent / kept on the vehicle</span><span class="v">${r.bytes_sent} B · ${r.kept_local_pct}% kept local</span></div>
    <div class="row"><span class="k">Packets acknowledged / retries</span><span class="v">${r.packets_acked} / ${r.retries}</span></div>${log}`;
}
async function authorize() {
  const dest = S.facts["transport.destination"]?.value || prompt("Destination hospital?", "Valley Medical");
  if (dest) await api("/api/relay/authorize", { method: "POST", body: JSON.stringify({ destination: dest, scope: "stroke pre-alert set" }) });
}
document.addEventListener("keydown", (e) => {   // presenter hotkeys for the emulated link
  if (!e.shiftKey || e.target.tagName === "INPUT") return;
  const mode = { KeyG: "good", KeyW: "weak", KeyD: "down" }[e.code];
  if (mode) fetch(`/api/netem/${mode}`, { method: "POST" });
});

function renderClocks() {
  if (!S) return;
  const now = Date.now();
  $("clocks").innerHTML = S.clocks.map((c) => {
    let secs = c.since ? (now - new Date(c.since)) / 1000 : (new Date(c.until) - now) / 1000;
    const neg = secs < 0; secs = Math.abs(Math.round(secs));
    const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
    const t = `${h ? h + ":" : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(s).padStart(2, "0")}`;
    const label = c.since ? `${esc(c.label)} +` : `${esc(c.label)} in`;
    return `<div class="clock ${c.until && neg ? "overdue" : ""}"><span>${label}</span><b>${c.until && neg ? "overdue " : ""}${t}</b></div>`;
  }).join("");
}
setInterval(renderClocks, 1000);

// ---- push-to-talk: record PCM, encode 16 kHz WAV, POST /api/audio ----
let rec = null;
async function startRec(by) {
  if (rec) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    const ctx = new AudioContext();
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    src.connect(proc); proc.connect(ctx.destination);
    rec = { stream, ctx, proc, chunks, by };
    $(by === "medic" ? "ptt-medic" : "ptt-other").classList.add("on");
    $("rec").textContent = "● recording";
  } catch (err) {
    $("rec").textContent = "mic blocked: open via http://localhost (port forward) or https";
  }
}
async function stopRec() {
  if (!rec) return;
  const { stream, ctx, proc, chunks, by } = rec; rec = null;
  proc.disconnect(); stream.getTracks().forEach((t) => t.stop());
  const sr = ctx.sampleRate; await ctx.close();
  document.querySelectorAll(".ptt").forEach((b) => b.classList.remove("on"));
  $("rec").textContent = "transcribing…";
  const wav = encodeWav(downsample(concat(chunks), sr, 16000), 16000);
  const fd = new FormData();
  fd.append("file", new Blob([wav], { type: "audio/wav" }), "clip.wav");
  fd.append("captured_by", by);
  if (by === "other") fd.append("speaker", $("speaker").value || "family member");
  try { await fetch("/api/audio", { method: "POST", body: fd }); } finally { $("rec").textContent = ""; }
}
for (const [id, by] of [["ptt-medic", "medic"], ["ptt-other", "other"]]) {
  const b = $(id);
  b.addEventListener("mousedown", () => startRec(by)); b.addEventListener("touchstart", (e) => { e.preventDefault(); startRec(by); });
  b.addEventListener("mouseup", stopRec); b.addEventListener("mouseleave", stopRec); b.addEventListener("touchend", stopRec);
}
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.repeat) return;
  if (e.code === "Space") { e.preventDefault(); startRec("medic"); }
  if (e.code === "KeyF") startRec("other");
});
document.addEventListener("keyup", (e) => { if (e.code === "Space" || e.code === "KeyF") stopRec(); });

// ---- typed input, simulated monitor, new incident ----
$("typed").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("typed-text").value.trim(); if (!text) return;
  const by = $("typed-by").value;
  await api("/api/transcript", { method: "POST", body: JSON.stringify({ text, captured_by: by, speaker: by === "other" ? ($("speaker").value || null) : null }) });
  $("typed-text").value = "";
});
$("monitor").addEventListener("submit", async (e) => {
  e.preventDefault();
  const facts = [];
  for (const el of e.target.elements) {
    if (!el.name || el.value === "") continue;
    const value = el.name === "vitals.on_oxygen" ? el.value === "true" : Number(el.value);
    facts.push({ key: el.name, value, captured_by: "device", role: "device", speaker: "monitor", confidence: 0.99, provenance: { extractor: "manual" } });
  }
  if (facts.length) await api("/api/facts", { method: "POST", body: JSON.stringify(facts) });
  e.target.reset();
});
$("incident").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/incident", { method: "POST", body: JSON.stringify({ dispatch: e.target.dispatch.value || null }) });
});
fetch("/api/health").then((r) => r.json()).then((h) => { $("llm").textContent = `LLM: ${h.llm_model || "rules only"}`; });
connect();
