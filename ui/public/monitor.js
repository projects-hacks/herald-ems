const readings = document.getElementById("readings"), phase = document.getElementById("phase");
const play = document.getElementById("play");
let index = 0, timer = null;
try {
  const response = await fetch("/fixtures/monitor_journey.json");
  if (!response.ok) throw new Error("Synthetic scenario unavailable");
  const scenario = await response.json();
  const fields = scenario.readings.map(({ key, label, unit }) => {
    const card = document.createElement("article"), title = document.createElement("h1"), value = document.createElement("strong"), units = document.createElement("small");
    title.textContent = label; units.textContent = unit;
    card.append(title, value, units); readings.append(card);
    return { key, value };
  });
  function render() {
    fields.forEach(({ key, value }) => { value.textContent = scenario.steps[index][key]; });
    phase.textContent = `Synthetic step ${index + 1} of ${scenario.steps.length} · ${timer ? `changes every ${scenario.step_seconds} seconds` : "paused"}`;
    play.textContent = timer ? "Pause changes" : "Start changes";
  }
  function pause() { clearInterval(timer); timer = null; }
  function next() { if (index < scenario.steps.length - 1) index++; else pause(); render(); }
  play.onclick = () => { if (timer) pause(); else { if (index === scenario.steps.length - 1) index = 0; timer = setInterval(next, scenario.step_seconds * 1000); } render(); };
  document.getElementById("next").onclick = () => { pause(); next(); };
  document.getElementById("reset").onclick = () => { pause(); index = 0; render(); };
  document.getElementById("fullscreen").onclick = () => { void document.documentElement.requestFullscreen().catch(() => { phase.textContent = "Full screen unavailable; the monitor still works in this window."; }); };
  document.addEventListener("visibilitychange", () => { if (document.hidden) { pause(); render(); } });
  render();
} catch (error) { phase.textContent = error.message; document.querySelectorAll("button").forEach((button) => { button.disabled = true; }); }
