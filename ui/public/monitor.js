const readings = document.getElementById("readings"), phase = document.getElementById("phase"), scenarioName = document.getElementById("scenario");
const play = document.getElementById("play");
let index = 0, timer = null;
try {
  const response = await fetch("/fixtures/monitor_journey.json");
  if (!response.ok) throw new Error("Synthetic scenario unavailable");
  const scenario = await response.json();
  const { tick_ms: tickMs, simulated_minutes_per_tick: minutesPerTick } = scenario.display;
  const startMinute = scenario.simulated_minutes.start, endMinute = scenario.simulated_minutes.end;
  const sampleCount = Math.round((endMinute - startMinute) / minutesPerTick) + 1;
  function valueAt(key, minute) {
    const after = scenario.steps.findIndex((step) => step.minute >= minute);
    if (after <= 0) return scenario.steps[0][key];
    const before = scenario.steps[after - 1], next = scenario.steps[after];
    const fraction = (minute - before.minute) / (next.minute - before.minute);
    return Math.round(before[key] + (next[key] - before[key]) * fraction);
  }
  const samples = Array.from({ length: sampleCount }, (_, sampleIndex) => {
    const minute = startMinute + sampleIndex * minutesPerTick;
    return { minute, ...Object.fromEntries(scenario.readings.map(({ key }) => [key, valueAt(key, minute)])) };
  });
  scenarioName.textContent = scenario.scenario_label || "Synthetic training scenario";
  const fields = scenario.readings.map(({ key, label, unit }) => {
    const card = document.createElement("article"), title = document.createElement("h1"), value = document.createElement("strong"), units = document.createElement("small"), chart = document.createElementNS("http://www.w3.org/2000/svg", "svg"), trend = document.createElement("p");
    title.textContent = label; units.textContent = unit;
    chart.classList.add("trend-chart"); chart.setAttribute("viewBox", "0 0 300 88"); chart.setAttribute("role", "img");
    trend.classList.add("trend-label");
    card.append(title, value, units, chart, trend); readings.append(card);
    return { key, value, chart, trend, values: samples.map((sample) => sample[key]), label, unit };
  });
  function drawTrend(field) {
    const { values, chart } = field, shown = values.slice(0, index + 1);
    const low = Math.min(...values), high = Math.max(...values), padding = Math.max((high - low) * 0.12, 1);
    const min = low - padding, max = high + padding, width = 264, height = 50, left = 28, top = 14;
    const point = (value, i) => `${left + (shown.length === 1 ? width / 2 : i * width / (shown.length - 1))},${top + height - ((value - min) / (max - min)) * height}`;
    chart.replaceChildren();
    const grid = document.createElementNS(chart.namespaceURI, "path"), line = document.createElementNS(chart.namespaceURI, "polyline"), dot = document.createElementNS(chart.namespaceURI, "circle"), minLabel = document.createElementNS(chart.namespaceURI, "text"), maxLabel = document.createElementNS(chart.namespaceURI, "text");
    grid.setAttribute("d", `M ${left} ${top} H ${left + width} M ${left} ${top + height / 2} H ${left + width} M ${left} ${top + height} H ${left + width}`);
    grid.setAttribute("class", "trend-grid");
    line.setAttribute("points", shown.map(point).join(" ")); line.setAttribute("class", "trend-line");
    const [x, y] = point(shown.at(-1), shown.length - 1).split(","); dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("r", "4"); dot.setAttribute("class", "trend-dot");
    minLabel.setAttribute("x", "0"); minLabel.setAttribute("y", String(top + height)); minLabel.textContent = String(Math.round(low));
    maxLabel.setAttribute("x", "0"); maxLabel.setAttribute("y", String(top + 7)); maxLabel.textContent = String(Math.round(high));
    chart.append(grid, line, dot, minLabel, maxLabel);
    chart.setAttribute("aria-label", `${field.label} trend through synthetic minute ${samples[index].minute}: ${shown.join(", ")} ${field.unit}`);
    field.trend.textContent = `Trend: +${samples[0].minute} → +${samples[index].minute} min`;
  }
  function render() {
    fields.forEach((field) => { field.value.textContent = samples[index][field.key]; drawTrend(field); });
    phase.textContent = `Synthetic transport +${samples[index].minute} min · sample ${index + 1} of ${samples.length} · ${timer ? "updates every second" : "paused"}`;
    play.textContent = timer ? "Pause changes" : "Start changes";
  }
  function pause() { clearInterval(timer); timer = null; }
  function next() { if (index < samples.length - 1) index++; else pause(); render(); }
  play.onclick = () => { if (timer) pause(); else { if (index === samples.length - 1) index = 0; timer = setInterval(next, tickMs); } render(); };
  document.getElementById("next").onclick = () => { pause(); next(); };
  document.getElementById("reset").onclick = () => { pause(); index = 0; render(); };
  document.getElementById("fullscreen").onclick = () => { void document.documentElement.requestFullscreen().catch(() => { phase.textContent = "Full screen unavailable; the monitor still works in this window."; }); };
  document.addEventListener("visibilitychange", () => { if (document.hidden) { pause(); render(); } });
  render();
} catch (error) { phase.textContent = error.message; document.querySelectorAll("button").forEach((button) => { button.disabled = true; }); }
