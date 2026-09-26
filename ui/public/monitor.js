// The synthetic bedside monitor. A journey (fixtures/monitor_scenarios.json lists them; ?scenario=<id> picks one) gives
// the numbers over simulated transport time; the waveforms are drawn from those numbers: the ECG beats at the heart
// rate in the scenario's rhythm (sinus, ST elevation, atrial fibrillation), the pleth weakens as pressure falls, and the
// capnogram breathes at the respiratory rate with its plateau at the EtCO2. Visual test data only: it is not a
// physiological model and sends nothing to Herald; Herald's camera reads the numbers off the screen.
const $ = (id) => document.getElementById(id);
const phase = $("phase"), play = $("play");
const COLORS = { "vitals.hr": "#3ee07a", "vitals.sbp": "#ff6b6b", "vitals.dbp": "#ff9b9b", "vitals.spo2": "#3fd0f0",
  "vitals.rr": "#e8eef3", "vitals.etco2": "#f2c94c", "vitals.temp": "#e8eef3" };
let index = 0, timer = null;

try {
  // ---------- the journey ----------
  const listing = await fetch("/fixtures/monitor_scenarios.json");
  if (!listing.ok) throw new Error("Synthetic scenario list unavailable");
  const { default: fallback, scenarios } = await listing.json();
  const wanted = new URLSearchParams(location.search).get("scenario");
  const chosen = scenarios.find((s) => s.id === wanted) ?? scenarios.find((s) => s.id === fallback) ?? scenarios[0];
  // One button per scenario: pressing one loads it fresh from the start (pressing the one playing restarts it).
  for (const s of scenarios) {
    const button = document.createElement("button");
    button.type = "button"; button.textContent = s.label; button.setAttribute("aria-pressed", String(s.id === chosen.id));
    button.onclick = () => { const url = new URL(location.href); url.searchParams.set("scenario", s.id); location.assign(url); };
    $("picks").append(button);
  }
  const response = await fetch(chosen.file);
  if (!response.ok) throw new Error("Synthetic scenario unavailable");
  const scenario = await response.json();
  const { tick_ms: tickMs, simulated_minutes_per_tick: minutesPerTick } = scenario.display;
  const startMinute = scenario.simulated_minutes.start, endMinute = scenario.simulated_minutes.end;
  const sampleCount = Math.round((endMinute - startMinute) / minutesPerTick) + 1;
  const decimals = Object.fromEntries(scenario.readings.map((r) => [r.key, r.decimals ?? 0]));
  const round = (key, v) => Number(v.toFixed(decimals[key]));
  function valueAt(key, minute) {
    const after = scenario.steps.findIndex((step) => step.minute >= minute);
    if (after <= 0) return scenario.steps[0][key];
    const before = scenario.steps[after - 1], next = scenario.steps[after];
    return round(key, before[key] + (next[key] - before[key]) * (minute - before.minute) / (next.minute - before.minute));
  }
  const samples = Array.from({ length: sampleCount }, (_, i) => {
    const minute = startMinute + i * minutesPerTick;
    return { minute, ...Object.fromEntries(scenario.readings.map(({ key }) => [key, valueAt(key, minute)])) };
  });
  const timeLabel = (minute) => `+${Math.floor(minute)}:${String(Math.round((minute % 1) * 60)).padStart(2, "0")}`;
  $("scenario").textContent = scenario.scenario_label || "Synthetic training scenario";
  const rhythm = scenario.rhythm ?? { type: "sinus", label: "Sinus rhythm" };
  $("rhythm").textContent = rhythm.label;
  const current = () => samples[index];

  // ---------- numbers and trends ----------
  const trends = scenario.readings.map(({ key, label, unit }) => {
    const card = document.createElement("article"), title = document.createElement("h2");
    const chart = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    card.className = "trend"; title.textContent = label; chart.setAttribute("viewBox", "0 0 200 46");
    chart.setAttribute("role", "img"); card.append(title, chart); $("trends").append(card);
    return { key, label, unit, chart, values: samples.map((s) => s[key]) };
  });
  function drawTrend(t) {
    const shown = t.values.slice(0, index + 1), low = Math.min(...t.values), high = Math.max(...t.values);
    const pad = Math.max((high - low) * 0.15, 0.5), min = low - pad, max = high + pad;
    const pt = (v, i) => `${shown.length === 1 ? 100 : (i * 200) / (t.values.length - 1)},${44 - ((v - min) / (max - min)) * 40}`;
    const ns = t.chart.namespaceURI, line = document.createElementNS(ns, "polyline"), dot = document.createElementNS(ns, "circle");
    line.setAttribute("points", shown.map(pt).join(" ")); line.setAttribute("stroke", COLORS[t.key] ?? "#e8eef3");
    const [x, y] = pt(shown.at(-1), shown.length - 1).split(",");
    dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("r", "3.5"); dot.setAttribute("fill", COLORS[t.key] ?? "#e8eef3");
    t.chart.replaceChildren(line, dot);
    t.chart.setAttribute("aria-label", `${t.label} trend: ${shown.join(", ")} ${t.unit}`);
  }
  function render() {
    const s = current();
    document.querySelectorAll("[data-key]").forEach((el) => {
      const v = s[el.dataset.key];
      el.textContent = v === undefined ? "--" : Number(v).toFixed(decimals[el.dataset.key] ?? 0);
    });
    trends.forEach(drawTrend);
    phase.textContent = `Synthetic transport ${timeLabel(s.minute)} · sample ${index + 1} of ${samples.length} · ${timer ? "updates every second" : "paused"}`;
    play.textContent = timer ? "Pause changes" : "Start changes";
  }
  function pause() { clearInterval(timer); timer = null; }
  function next() { if (index < samples.length - 1) index++; else pause(); render(); }
  play.onclick = () => { if (timer) pause(); else { if (index === samples.length - 1) index = 0; timer = setInterval(next, tickMs); } render(); };
  $("next").onclick = () => { pause(); next(); };
  $("reset").onclick = () => { pause(); index = 0; render(); };
  $("fullscreen").onclick = () => { void document.documentElement.requestFullscreen().catch(() => { phase.textContent = "Full screen unavailable; the monitor still works in this window."; }); };
  document.addEventListener("visibilitychange", () => { if (document.hidden) { pause(); render(); } });
  render();

  // ---------- waveforms ----------
  const g = (t, mu, sd) => Math.exp(-((t - mu) ** 2) / (2 * sd * sd));
  const beats = [];                          // R-peak times (s)
  let nextBeat = 0, nextBreath = 0, breathStart = 0, breathLen = 3;
  function schedule(now) {
    const hr = Math.max(30, current()["vitals.hr"] ?? 80);
    while (nextBeat <= now + 0.5) {
      beats.push(nextBeat);
      const rr = 60 / hr;
      nextBeat += rhythm.type === "af" ? rr * (0.65 + Math.random() * 0.7) : rr;   // AF: irregularly irregular
    }
    while (beats.length > 6) beats.shift();
    const rr = Math.max(6, current()["vitals.rr"] ?? 16);
    if (now >= nextBreath) { breathStart = nextBreath; breathLen = 60 / rr; nextBreath = breathStart + breathLen; }
  }
  function ecg(t) {
    let v = 0;
    for (const b of beats) {
      const d = t - b, sc = Math.min(1, Math.max(0.55, (60 / (current()["vitals.hr"] ?? 80)) / 0.8));
      if (d < -0.3 || d > 0.6) continue;
      if (rhythm.type !== "af") v += 0.12 * g(d, -0.16 * sc, 0.025);                 // P wave
      v += -0.12 * g(d, -0.028, 0.009) + 1.0 * g(d, 0, 0.011) - 0.28 * g(d, 0.032, 0.011);   // QRS
      if (rhythm.type === "stemi") v += 0.32 * (1 / (1 + Math.exp(-(d - 0.05) / 0.012))) * (1 - 1 / (1 + Math.exp(-(d - 0.3 * sc) / 0.04)));  // ST elevation
      v += (rhythm.type === "stemi" ? 0.42 : 0.28) * g(d, 0.26 * sc, 0.05 * sc);       // T wave
    }
    if (rhythm.type === "af") v += 0.035 * Math.sin(2 * Math.PI * 6.3 * t) + 0.025 * Math.sin(2 * Math.PI * 9.1 * t + 1);   // fibrillatory baseline
    return v;
  }
  function pleth(t) {
    const perf = Math.min(1, Math.max(0.3, ((current()["vitals.sbp"] ?? 110) - 55) / 60));
    let v = 0;
    for (const b of beats) { const d = t - b - 0.2; if (d > -0.1 && d < 0.9) v += perf * (g(d, 0.12, 0.06) + 0.32 * g(d, 0.34, 0.07)); }
    return v;
  }
  function co2(t) {
    const u = (t - breathStart) / breathLen, h = Math.min(1, (current()["vitals.etco2"] ?? 35) / 45);
    if (u < 0 || u > 1) return 0;
    if (u < 0.06) return h * (u / 0.06);                         // expiratory upstroke
    if (u < 0.46) return h * (0.93 + 0.07 * ((u - 0.06) / 0.4)); // plateau, slight upslope to EtCO2
    if (u < 0.52) return h * (1 - (u - 0.46) / 0.06);            // inspiration
    return 0;
  }
  const strips = [
    { canvas: $("wave-ecg"), f: ecg, color: "#3ee07a", lo: -0.45, hi: 1.25 },
    { canvas: $("wave-pleth"), f: pleth, color: "#3fd0f0", lo: -0.1, hi: 1.25 },
    { canvas: $("wave-co2"), f: co2, color: "#f2c94c", lo: -0.08, hi: 1.12 },
  ];
  const SWEEP_S = 6;                          // seconds across the screen
  for (const s of strips) {
    const ctx = s.canvas.getContext("2d"), dpr = window.devicePixelRatio || 1;
    const size = () => { s.w = s.canvas.clientWidth; s.h = s.canvas.clientHeight; s.canvas.width = s.w * dpr; s.canvas.height = s.h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, s.w, s.h); s.lastX = null; };
    size(); window.addEventListener("resize", size);
    s.ctx = ctx;
  }
  const t0 = performance.now() / 1000;
  let lastT = 0;
  function frame() {
    const t = performance.now() / 1000 - t0;
    schedule(t);
    for (const s of strips) {
      const { ctx, w, h } = s;
      const xAt = (tt) => ((tt % SWEEP_S) / SWEEP_S) * w, yAt = (v) => h - 8 - ((v - s.lo) / (s.hi - s.lo)) * (h - 16);
      const x1 = xAt(t);
      ctx.fillStyle = "#000"; ctx.fillRect(x1, 0, Math.min(18, w - x1), h);     // the sweep's erase gap
      ctx.strokeStyle = s.color; ctx.lineWidth = 2.2; ctx.lineJoin = "round"; ctx.beginPath();
      const steps = Math.max(2, Math.ceil((t - lastT) * 250));
      for (let i = 0; i <= steps; i++) {
        const tt = lastT + ((t - lastT) * i) / steps, x = xAt(tt), y = yAt(s.f(tt));
        if (i === 0 || x < s.lastX) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        s.lastX = x;
      }
      ctx.stroke();
    }
    lastT = t;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  setInterval(() => { const d = new Date(); $("clock").textContent = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`; }, 1000);
} catch (error) { phase.textContent = error.message; document.querySelectorAll("button").forEach((button) => { button.disabled = true; }); }
