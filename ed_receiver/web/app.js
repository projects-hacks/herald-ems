import { esc, formatValue, newestPatient, isNewField, fieldKeys, observedElapsed, hhmm } from './view.mjs';
import { renderJourney } from './journey.mjs';
const $ = (id) => document.getElementById(id);
let selected = null, manualSelection = false, lastView = null, labels = {}, display = null, reportVersion = '', reportAbort = null;
const seen = {}, highlights = {}, triageRank = { immediate: 0, delayed: 1, minimal: 2, expectant: 3, dead: 4 };
fetch('/api/meta').then((r) => { if (!r.ok) throw new Error(); return r.json(); }).then((meta) => { labels = meta.keys; display = meta.display; document.documentElement.style.setProperty('--critical-size', `${display.critical_px}px`); document.documentElement.style.setProperty('--body-size', `${display.body_px}px`); if (lastView) render(lastView); }).catch(() => {});
const label = (key) => labels[key]?.label ?? key;
const triage = (incident) => incident.fields['triage.category']?.v ?? 'unknown';

async function loadReport(id, version, format = '') {
  reportAbort?.abort(); reportAbort = new AbortController();
  const token = reportAbort, container = $('report'); container.hidden = false; container.textContent = 'Loading received-data report…';
  const timer = setTimeout(() => token.abort(), 5000);
  try {
    const r = await fetch(`/api/handoff/${encodeURIComponent(id)}${format ? `?format=${encodeURIComponent(format)}` : ''}`, { signal: token.signal });
    if (!r.ok) throw new Error();
    const report = await r.json();
    if (selected !== id || token !== reportAbort || token.signal.aborted) return;
    container.innerHTML = `<h2>${esc(report.format.title)} · received data</h2><p>${esc(report.scope)}</p><label>Format <select id="report-format"><option value="">Automatic</option>${report.formats.map((f) => `<option value="${esc(f.id)}" ${format === f.id ? 'selected' : ''}>${esc(f.label)}</option>`).join('')}</select></label>${report.sections.map((s) => `<section><h3>${esc(s.label)}</h3><ul>${s.lines.map((l) => `<li>${esc(l.text)}</li>`).join('')}</ul></section>`).join('')}<p>Not yet known: ${esc(report.not_yet_known.map((f) => f.label).join(' · ') || 'No additional listed gaps')}</p>`;
    $('report-format').onchange = (event) => loadReport(id, version, event.target.value);
  } catch { if (selected === id && token === reportAbort) { container.textContent = 'Received-data report unavailable. '; const retry = document.createElement('button'); retry.textContent = 'Retry'; retry.onclick = () => loadReport(id, version, format); container.append(retry); } }
  finally { clearTimeout(timer); }
}
async function acknowledge(id, status) {
  const note = window.prompt(status === 'cath_lab_activated' ? 'Optional cath-lab note' : 'Optional receipt note');
  if (note === null) return;
  try {
    const r = await fetch(`/incidents/${encodeURIComponent(id)}/acknowledgements`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, note: note || null }),
    });
    if (!r.ok) throw new Error();
  } catch { window.alert('Acknowledgement was not recorded. Check the ED receiver connection.'); }
}
function render(view) {
  lastView = view;
  contact();
  const newest = newestPatient(view.incidents);
  if (!newest) { $('root').textContent = 'No incoming patients. Waiting for the ambulance…'; $('patients').replaceChildren(); $('report').hidden = true; $('banner').hidden = true; selected = null; reportVersion = ''; return; }
  if (!manualSelection || !view.incidents[selected]) selected = newest;
  const incident = view.incidents[selected], max = Math.max(0, ...incident.applied), prior = seen[selected] ?? 0;
  if (max > prior && display) highlights[selected] = { until: Date.now() + display.highlight_ms, keys: new Set(fieldKeys(incident).filter((key) => isNewField(incident.fields[key], prior))) };
  const recent = highlights[selected]?.until > Date.now() ? highlights[selected].keys : new Set();
  const ids = Object.keys(view.incidents).sort((a, b) => (triageRank[triage(view.incidents[a])] ?? 1) - (triageRank[triage(view.incidents[b])] ?? 1) || view.incidents[b].first_at.localeCompare(view.incidents[a].first_at));
  $('patients').innerHTML = ids.map((id, i) => `<button data-index="${i}" aria-pressed="${id === selected}"><span class="triage">${esc(triage(view.incidents[id]))}</span> · ${esc(view.incidents[id].label || id)}</button>`).join('');
  $('patients').querySelectorAll('button').forEach((b) => b.onclick = () => { selected = ids[Number(b.dataset.index)]; manualSelection = true; render(lastView); });
  $('banner').hidden = !recent.size;
  $('banner').textContent = `UPDATE · ${incident.label || selected} · ${incident.dest || 'Destination not received'}`;
  // A time value reads "13:04 · 1 h 12 m ago"; other values carry the key's unit ("142 mg/dL"). The label span
  // stays the only span in the row, so the `.new span::after` "· NEW" marker keeps landing on the label alone.
  const row = (key) => {
    const field = incident.fields[key], meta = labels[key] ?? {};
    const elapsed = field && key === 'stroke.lkw' ? observedElapsed(incident.lkw_at) : null;
    const value = !field ? '<span class="empty">not received</span>'
      : elapsed !== null ? esc(`${formatValue(field.v)} · ${elapsed} ago`)
      : esc(`${formatValue(field.v)}${meta.unit ? ` ${meta.unit}` : ''}${key === 'stroke.lkw' ? ' · elapsed not received' : ''}`);
    return `<div class="row ${recent.has(key) ? 'new' : ''}"><span>${esc(label(key))}</span><b${elapsed !== null ? ` data-clock="${esc(String(field.v))}" data-since="${esc(incident.lkw_at)}"` : ''}>${value}</b></div>`;
  };
  const acknowledgements = incident.acknowledgements || [];
  $('root').innerHTML = `<div class="grid"><section class="card"><h2>${esc(incident.label || selected)} · received facts</h2>${fieldKeys(incident).map(row).join('') || '<p>No fields received yet</p>'}</section><section class="card"><h2>Link and packets</h2><p>${incident.applied.length} packets · ${incident.duplicates} duplicates ignored</p><p>${incident.queued_on_rig} queued on the vehicle · ${incident.bytes} bytes received</p><p><button id="ack-received">Mark received</button> <button id="ack-cath">Cath lab activated</button></p>${acknowledgements.length ? `<p>Clinician acknowledgement: ${esc(acknowledgements.at(-1).status.replaceAll('_', ' '))}</p>` : '<p>No clinician acknowledgement recorded.</p>'}<details><summary>Packet history</summary>${[...incident.packets].reverse().map((p) => `<p class="packet">${esc(incident.label || selected)} · #${p.seq} · ${esc(p.tier)} · ${p.bytes} B<br>${esc(p.keys.map(label).join(' · '))}</p>`).join('')}</details></section></div>${incident.timeline.length ? `<details class="card"><summary>Received event history</summary>${incident.timeline.map((t) => `<p>${esc(hhmm(t.t))} · ${esc(label(t.k))}: ${esc(formatValue(t.v))}</p>`).join('')}</details>` : ''}`;
  $('ack-received').onclick = () => acknowledge(selected, 'received');
  $('root').insertAdjacentHTML('beforeend', renderJourney(incident, labels));
  $('ack-cath').onclick = () => acknowledge(selected, 'cath_lab_activated');
  seen[selected] = max;
  const factsSection = $('root').querySelector('section');
  const critical = display?.critical_keys ?? [];
  factsSection.innerHTML = `<h2>${esc(incident.label || selected)} · Critical</h2><div class="critical">${critical.map(row).join('')}</div><h2>Vitals, exam, logistics</h2>${fieldKeys(incident).filter((key) => !critical.includes(key)).map(row).join('')}`;
  const version = `${selected}:${max}`;
  if (reportVersion !== version) { reportVersion = version; void loadReport(selected, version); }
  contact();
}
function contact() {
  const at = lastView?.last_contact_at;
  $('contact').textContent = at ? `Last vehicle contact: ${hhmm(at)} · ${Math.max(0, Math.floor((Date.now() - new Date(at).getTime()) / 1000))} s ago` : 'Last vehicle contact: unknown';
}
function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { $('connection').textContent = 'ED screen connected'; };
  ws.onmessage = (e) => { const data = JSON.parse(e.data); if (data.incidents) render(data); };
  ws.onclose = () => { $('connection').textContent = 'SCREEN OFFLINE · showing last received data'; setTimeout(connect, 1000); };
}
function tickClocks() {
  document.querySelectorAll('b[data-clock]').forEach((el) => {
    const elapsed = observedElapsed(el.dataset.since);
    if (elapsed !== null) el.textContent = `${el.dataset.clock} · ${elapsed} ago`;
  });
}
setInterval(() => { contact(); tickClocks(); if (lastView && selected && highlights[selected]?.until <= Date.now()) { delete highlights[selected]; render(lastView); } }, 1000);
connect();
