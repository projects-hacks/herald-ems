import { esc, formatValue, newestPatient, isNewField, fieldKeys, observedElapsed, hhmm, alertBadges, ageSex, vitalTile, sparkline, careEvents } from './view.mjs';
import { renderJourney } from './journey.mjs';
import { renderHandover } from './handover.mjs';
// The ED "incoming ambulance" board. It shows only what the ambulance sent: every empty slot says "not received".
// Layout and which keys go where come from config/ed_display.yaml (GET /api/meta), never from literals here.
const $ = (id) => document.getElementById(id);
let selected = null, manualSelection = false, lastView = null, labels = {}, display = null, reportVersion = '', reportAbort = null;
const seen = {}, highlights = {}, triageRank = { immediate: 0, delayed: 1, minimal: 2, expectant: 3, dead: 4 };
fetch('/api/meta').then((r) => { if (!r.ok) throw new Error(); return r.json(); }).then((meta) => { labels = meta.keys; display = meta.display; if (lastView) render(lastView); }).catch(() => {});
const label = (key) => labels[key]?.label ?? key;
const unitOf = (key) => labels[key]?.unit ? ` ${labels[key].unit}` : '';
const triage = (incident) => incident.fields[display?.header?.triage ?? 'triage.category']?.v ?? 'unknown';
const NOT_RECEIVED = '<span class="empty">not received</span>';

async function loadReport(id, version, format = '') {
  reportAbort?.abort(); reportAbort = new AbortController();
  const token = reportAbort, container = $('report'); $('report-box').hidden = false; container.textContent = 'Loading received-data report…';
  const timer = setTimeout(() => token.abort(), 5000);
  try {
    const r = await fetch(`/api/handoff/${encodeURIComponent(id)}${format ? `?format=${encodeURIComponent(format)}` : ''}`, { signal: token.signal });
    if (!r.ok) throw new Error();
    const report = await r.json();
    if (selected !== id || token !== reportAbort || token.signal.aborted) return;
    container.innerHTML = `<h2>${esc(report.format.title)} · received data</h2><p class="muted">${esc(report.scope)}</p><label>Format <select id="report-format"><option value="">Automatic</option>${report.formats.map((f) => `<option value="${esc(f.id)}" ${format === f.id ? 'selected' : ''}>${esc(f.label)}</option>`).join('')}</select></label>${report.sections.map((s) => `<section><h3>${esc(s.label)}</h3><ul>${s.lines.map((l) => `<li>${esc(l.text)}</li>`).join('')}</ul></section>`).join('')}<p class="muted">Not yet known: ${esc(report.not_yet_known.map((f) => f.label).join(' · ') || 'No additional listed gaps')}</p>`;
    $('report-format').onchange = (event) => loadReport(id, version, event.target.value);
  } catch { if (selected === id && token === reportAbort) { container.textContent = 'Received-data report unavailable. '; const retry = document.createElement('button'); retry.textContent = 'Retry'; retry.onclick = () => loadReport(id, version, format); container.append(retry); } }
  finally { clearTimeout(timer); }
}
async function acknowledge(id, status, askNote = true) {
  const note = askNote ? window.prompt(status === 'cath_lab_activated' ? 'Optional cath-lab note' : 'Optional receipt note') : '';
  if (note === null) return;
  try {
    const r = await fetch(`/incidents/${encodeURIComponent(id)}/acknowledgements`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, note: note || null }),
    });
    if (!r.ok) throw new Error();
  } catch { window.alert('Acknowledgement was not recorded. Check the ED receiver connection.'); }
}

// ---------- arrival ----------
/** The road-route arrival time when the vehicle sends one; otherwise the crew's spoken estimate from when it arrived. */
function arrivalOf(incident) {
  const f = incident.fields, eta = f['transport.eta_min'], routed = f['transport.eta_at'];
  const at = routed ? new Date(routed.v).getTime() : eta && typeof eta.v === 'number' ? new Date(eta.t).getTime() + eta.v * 60000 : null;
  return Number.isFinite(at) ? { at, routed: Boolean(routed) } : null;
}
// Minutes to arrival, never a clock-looking "10:22" beside the arrival clock time; overdue says so.
const countdown = (arrival) => {
  const s = Math.round((arrival - Date.now()) / 1000);
  return s >= 60 ? `${Math.floor(s / 60)} min` : s > 0 ? '<1 min' : `due +${Math.floor(-s / 60)} min`;
};

// ---------- the pre-alert banner ----------
/** Every patient on the way opens with one banner across the board: who, where, when, and one action. The action is
 *  the pre-alert acknowledgement (config/ed_display.yaml `pre_alert`), or, while an alert that asks the ED to act is
 *  live, that alert's own (`activate`: the cath lab for a STEMI). The acknowledgement goes back to the crew. */
function activation(incident, badges) {
  if (incident.handover || incident.fields['encounter.disposition']) return null;
  const badge = badges.find((b) => b.activate), act = badge?.activate ?? display?.pre_alert;
  if (!act) return null;
  const done = (incident.acknowledgements ?? []).filter((a) => a.status === act.ack).at(-1);
  const lead = badge ?? badges[0], title = lead ? lead.text : 'Incoming ambulance', detail = lead?.detail ?? '';
  const hdr = display?.header ?? {}, demo = ageSex(incident.fields, hdr), arrival = arrivalOf(incident);
  const dest = incident.dest || incident.fields[hdr.destination ?? 'transport.destination']?.v;
  const html = `<section class="activate ${done ? 'done' : ''}" aria-live="assertive">
    <div class="act-text"><small>${done ? 'Pre-alert acknowledged' : 'New pre-alert · incoming ambulance'}</small>
      <b>${esc(title)} · ${esc(incident.label || selected)}${demo ? ` · ${esc(demo)}` : ''}</b>
      <span>${dest ? `to ${esc(formatValue(dest))}` : 'destination not received'}${arrival ? ` · ETA <b data-arrival="${arrival.at}">${countdown(arrival.at)}</b>` : ''}${detail ? ` · ${esc(detail)}` : ''}</span></div>
    ${done ? `<p class="act-done"><b>✓ ${esc(act.done)} ${esc(hhmm(done.at))}</b><span>The ambulance crew sees this</span></p>`
      : `<button id="ack-activate" class="act-btn" type="button">${esc(act.label)}</button>`}
  </section>`;
  return { html, ack: act.ack };
}

// ---------- sections ----------
function header(incident, badges, act = null) {
  const f = incident.fields, hdr = display?.header ?? {};
  const what = f['impression.primary']?.v ?? f['complaint.chief']?.v;
  const destKey = hdr.destination ?? 'transport.destination';
  const dest = incident.dest || f[destKey]?.v;
  const who = esc(incident.label || selected), demo = ageSex(f, hdr);
  const outcome = f['encounter.disposition'], handedOver = incident.handover, arrival = arrivalOf(incident);
  const tri = triage(incident);
  const state = handedOver ? 'handed-over' : outcome ? 'not-coming' : 'incoming';
  const lead = { 'handed-over': 'Handed over', 'not-coming': 'NOT COMING', incoming: 'Incoming' }[state];
  const badgeHtml = badges.map((b) => `<span class="badge ${esc(b.tone)}"><b>${esc(b.text)}</b>${b.detail ? `<small>${esc(b.detail)}</small>` : ''}</span>`).join('');
  const eta = state === 'handed-over' ? `<small>Handed over</small><b>${esc(hhmm(handedOver.at))}</b><span>final report received</span>`
    : state === 'not-coming' ? `<small>ETA</small><b>—</b><span>no transport to this hospital</span>`
    : arrival ? `<small>ETA ${arrival.routed ? '· road route' : '· crew estimate'}</small><b data-arrival="${arrival.at}">${countdown(arrival.at)}</b><span>arrives ${esc(hhmm(arrival.at))}</span>`
    : `<small>ETA</small><b>—</b><span>ETA not received</span>`;
  const acks = incident.acknowledgements ?? [];
  const last = (status) => acks.filter((a) => a.status === status).at(-1);
  const received = last('received'), cath = last('cath_lab_activated');
  return `<section id="incoming" class="incoming ${state}" aria-live="polite">
    <div class="who-block">
      ${what ? `<div class="kicker">${esc(String(formatValue(what)).toUpperCase())}</div>` : ''}
      <h1 class="who"><span class="lead">${esc(lead)} ·</span> ${who}<span class="demo">${demo ? ` · ${esc(demo)}` : ' · <span class="empty">age/sex not received</span>'}</span></h1>
      <div class="dest">${state === 'not-coming' ? esc(formatValue(outcome.v)) : dest ? `${state === 'handed-over' ? 'at' : 'to'} <b>${esc(formatValue(dest))}</b>` : '<span class="empty">destination not received</span>'}${tri !== 'unknown' ? ` <span class="triage ${esc(tri)}">${esc(tri)}</span>` : ''}</div>
      ${badgeHtml ? `<div class="badges">${badgeHtml}</div>` : ''}
    </div>
    <div class="side"><div class="eta">${eta}</div>
      <div class="actions">${act?.ack === 'received' ? '' : `<button id="ack-received" class="${received ? 'done' : ''}">${received ? `✓ Received ${esc(hhmm(received.at))}` : 'Mark received'}</button>`}
      ${act?.ack === 'cath_lab_activated' || !badges.some((b) => b.activate?.ack === 'cath_lab_activated') ? '' : `<button id="ack-cath" class="cath ${cath ? 'done' : ''}">${cath ? `✓ Cath lab ${esc(hhmm(cath.at))}` : 'Cath lab activated'}</button>`}</div></div>
  </section>`;
}

function safety(incident, recent) {
  const keys = display?.safety ?? [];
  if (!keys.length) return '';
  return `<section class="safety" aria-label="Safety"><h2 class="strip-title">Safety</h2>${keys.map((key) => {
    const field = incident.fields[key];
    return `<div class="safety-item ${field ? 'has' : 'missing'} ${recent.has(key) ? 'new' : ''}"><small>${esc(label(key))}</small><b>${field ? esc(`${formatValue(field.v)}${unitOf(key)}`) : NOT_RECEIVED}</b></div>`;
  }).join('')}</section>`;
}

function vitals(incident, recent) {
  const tiles = (display?.vitals ?? []).map((spec) => vitalTile(spec, incident, labels));
  const latest = tiles.filter((t) => !t.missing).map((t) => t.at).sort().at(-1);
  const arrow = { 1: '▲', '-1': '▼', 0: '' };
  const body = tiles.map((t) => {
    if (t.missing) return `<div class="vital missing"><small>${esc(t.short)}</small><b>—</b><span class="meta">not received</span></div>`;
    const line = sparkline(t.points, 120, 30);
    const fresh = t.keys.some((key) => recent.has(key));
    return `<div class="vital ${t.severity ?? ''} ${fresh ? 'new' : ''}"><small>${esc(t.short)}${t.severity ? `<em>${esc(t.severity)}</em>` : ''}</small>
      <b>${esc(t.value)}<span class="unit">${esc(t.unit)}</span></b>
      <span class="meta">${t.previous ? `<span class="dir">${arrow[t.direction]}</span> from ${esc(formatValue(t.previous.v))} · ` : ''}${esc(hhmm(t.at))}</span>
      ${line ? `<svg class="spark" viewBox="-3 -3 126 36" preserveAspectRatio="none" aria-hidden="true"><polyline points="${line}"/></svg>` : ''}</div>`;
  }).join('');
  return `<section class="vitals-wrap" aria-label="Latest vitals"><h2>Vitals <span class="muted">${latest ? `· last update ${esc(hhmm(latest))}` : '· none received'}</span></h2><div class="vitals">${body}</div></section>`;
}

function fieldValue(incident, key) {
  const field = incident.fields[key];
  const elapsed = key === 'stroke.lkw' ? observedElapsed(incident.lkw_at) : null;
  if (elapsed !== null) return `<b data-clock="${esc(formatValue(field.v))}" data-since="${esc(incident.lkw_at)}">${esc(`${formatValue(field.v)} · ${elapsed} ago`)}</b>`;
  return `<b>${esc(`${formatValue(field.v)}${unitOf(key)}${key === 'stroke.lkw' ? ' · elapsed not received' : ''}`)}</b>`;
}

function findings(incident, recent) {
  const keys = display?.findings ?? [], scores = display?.scores ?? [];
  const got = keys.filter((key) => incident.fields[key]), missing = keys.filter((key) => !incident.fields[key]);
  const rows = got.map((key) => `<div class="row ${recent.has(key) ? 'new' : ''}"><span>${esc(label(key))}</span>${fieldValue(incident, key)}</div>`).join('');
  const scoreRows = scores.filter((key) => incident.fields[key]).map((key) => `<div class="row score ${recent.has(key) ? 'new' : ''}"><span>${esc(label(key))}</span>${fieldValue(incident, key)}</div>`).join('');
  return `<section class="card findings"><h2>Findings</h2>${rows || '<p class="empty">No findings received yet</p>'}
    ${scoreRows ? `<h3>Scores and criteria</h3>${scoreRows}` : ''}
    ${missing.length ? `<p class="not-received"><b>Not received:</b> ${esc(missing.map(label).join(' · '))}</p>` : ''}</section>`;
}

function treatments(incident) {
  const events = careEvents(incident, display?.care ?? []);
  return `<section class="card care"><h2>Treatment given</h2>${events.length ? `<ol class="timeline">${events.map((e) =>
    `<li class="${esc(e.key.split('.')[0])}"><time>${esc(e.time)}</time><div><b>${esc(e.text)}</b><small>${esc(label(e.key))}${e.source === 'received' ? ' · time received here' : ''}</small></div></li>`).join('')}</ol>`
    : '<p class="empty">No medications or procedures received yet</p>'}</section>`;
}

function others(incident, recent, used) {
  const rest = fieldKeys(incident).filter((key) => !used.has(key));
  if (!rest.length) return '';
  return `<section class="card others"><h2>Also received</h2>${rest.map((key) => `<div class="row ${recent.has(key) ? 'new' : ''}"><span>${esc(label(key))}</span>${fieldValue(incident, key)}</div>`).join('')}</section>`;
}

function changed(incident, max) {
  // What the latest packet changed, in one line the charge nurse can read from across the room.
  const latest = fieldKeys(incident).filter((key) => incident.fields[key].seq === max && max > 0);
  if (!latest.length || incident.applied.length < 2) return '';
  const at = incident.packets.at(-1)?.at;
  return `<p class="changed"><span class="tag">Latest update${at ? ` ${esc(hhmm(at))}` : ''}</span>${latest.slice(0, 5).map((key) => {
    const h = incident.history?.[key] ?? [], was = h.length > 1 ? h[h.length - 2].v : null;
    const show = (v) => typeof v === 'object' && v !== null ? (Array.isArray(v) ? `${v.length} recorded` : '') : formatValue(v);
    return `<span><span class="k">${esc(label(key))}</span> ${was !== null && typeof was !== 'object' ? `<s>${esc(show(was))}</s> → ` : ''}<b>${esc(show(incident.fields[key].v))}${esc(typeof incident.fields[key].v === 'object' ? '' : unitOf(key))}</b></span>`;
  }).join('')}${latest.length > 5 ? `<span class="muted">+${latest.length - 5} more</span>` : ''}</p>`;
}

function link(incident) {
  const last = incident.packets.at(-1);
  return `<footer class="link"><details class="packets"><summary>Link · ${incident.applied.length} packets · ${incident.duplicates} duplicates ignored · ${incident.queued_on_rig} queued on the vehicle${last ? ` · last packet ${esc(hhmm(last.at))}` : ''}</summary>
    <p>${incident.bytes} bytes received</p>${[...incident.packets].reverse().map((p) => `<p class="packet">#${p.seq} · ${esc(p.tier)} · ${p.bytes} B · ${esc(hhmm(p.at))}<br>${esc(p.keys.map(label).join(' · '))}</p>`).join('')}</details></footer>`;
}

function history(incident) {
  const events = incident.timeline.length ? `<h3>Received event history</h3>${incident.timeline.map((t) => `<p>${esc(hhmm(t.t))} · ${esc(label(t.k))}: ${esc(formatValue(t.v))}</p>`).join('')}` : '';
  return `<details class="card history"><summary>Full received history</summary>${renderJourney(incident, labels)}${events}</details>`;
}

function patientList(view, ids) {
  $('patients').innerHTML = `<h2>Incoming · ${ids.length}</h2>${ids.map((id, i) => {
    const inc = view.incidents[id], tri = triage(inc), arrival = arrivalOf(inc), demo = ageSex(inc.fields, display?.header ?? {});
    const badge = alertBadges(inc.fields, display?.alerts, labels)[0];
    const status = inc.handover ? `handed over ${hhmm(inc.handover.at)}` : inc.fields['encounter.disposition'] ? 'not coming' : null;
    return `<button data-index="${i}" aria-pressed="${id === selected}" class="tri-${esc(tri)}"><span class="name">${esc(inc.label || id)}</span>
      <span class="sub">${demo ? esc(demo) : 'age/sex not received'}${badge ? ` · <em class="${esc(badge.tone)}">${esc(badge.text)}</em>` : ''}</span>
      <span class="sub">${status ? esc(status) : arrival ? `ETA <b data-arrival="${arrival.at}">${countdown(arrival.at)}</b>` : 'ETA not received'}</span></button>`;
  }).join('')}`;
  $('patients').querySelectorAll('button').forEach((b) => b.onclick = () => { selected = ids[Number(b.dataset.index)]; manualSelection = true; render(lastView); });
  $('patients').hidden = ids.length < 2;               // a patient picker only when there is more than one patient
}

function render(view) {
  lastView = view;
  contact();
  const newest = newestPatient(view.incidents);
  if (!newest) { $('root').innerHTML = '<p class="waiting">No incoming patients. Waiting for the ambulance…</p>'; $('patients').replaceChildren(); $('patients').hidden = true; $('report-box').hidden = true; selected = null; reportVersion = ''; return; }
  if (!manualSelection || !view.incidents[selected]) selected = newest;
  const incident = view.incidents[selected], max = Math.max(0, ...incident.applied), prior = seen[selected] ?? 0;
  if (max > prior && display) highlights[selected] = { until: Date.now() + display.highlight_ms, keys: new Set(fieldKeys(incident).filter((key) => isNewField(incident.fields[key], prior))) };
  const recent = highlights[selected]?.until > Date.now() ? highlights[selected].keys : new Set();
  const ids = Object.keys(view.incidents).sort((a, b) => (triageRank[triage(view.incidents[a])] ?? 1) - (triageRank[triage(view.incidents[b])] ?? 1) || view.incidents[b].first_at.localeCompare(view.incidents[a].first_at));
  patientList(view, ids);
  const badges = alertBadges(incident.fields, display?.alerts, labels);
  const hdr = display?.header ?? {};
  // Keys this board already shows in a named place; anything else the vehicle sent is listed under "Also received".
  const used = new Set([...Object.values(hdr), 'transport.eta_at', 'transport.eta_min', 'encounter.disposition', 'alert.readiness',
    'impression.primary', ...(display?.safety ?? []), ...(display?.vitals ?? []).flatMap((v) => v.keys), ...(display?.findings ?? []),
    ...(display?.scores ?? []), ...(display?.care ?? [])]);
  const open = new Set([...$('root').querySelectorAll('details[open]')].map((d) => d.className));   // survive a re-render
  const act = activation(incident, badges);
  $('root').innerHTML = `${act ? act.html : ''}${header(incident, badges, act)}${changed(incident, max)}${renderHandover(incident)}${safety(incident, recent)}${vitals(incident, recent)}
    <div class="columns">${findings(incident, recent)}${treatments(incident)}</div>${others(incident, recent, used)}${history(incident)}${link(incident)}`;
  $('root').querySelectorAll('details').forEach((d) => { if (open.has(d.className)) d.open = true; });
  if ($('ack-received')) $('ack-received').onclick = () => acknowledge(selected, 'received');
  if ($('ack-cath')) $('ack-cath').onclick = () => acknowledge(selected, 'cath_lab_activated');
  const actButton = $('ack-activate');
  if (act && actButton) actButton.onclick = () => { actButton.disabled = true; void acknowledge(selected, act.ack, false).finally(() => { actButton.disabled = false; }); };
  const handoverAck = $('ack-handover');
  if (handoverAck) handoverAck.onclick = () => { handoverAck.disabled = true; void acknowledge(selected, 'received', false).finally(() => { handoverAck.disabled = false; }); };
  seen[selected] = max;
  const version = `${selected}:${max}`;
  if (reportVersion !== version) { reportVersion = version; void loadReport(selected, version); }
}
function contact() {
  const at = lastView?.last_contact_at;
  const age = at ? Math.max(0, Math.floor((Date.now() - new Date(at).getTime()) / 1000)) : null;
  $('contact').textContent = at ? `Last vehicle contact ${hhmm(at)} · ${age} s ago` : 'Last vehicle contact: unknown';
  $('contact').classList.toggle('stale', age === null || age > 60);
  const now = new Date();
  $('clock').textContent = `${hhmm(now)}:${String(now.getSeconds()).padStart(2, '0')}`;
}
function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { $('connection').textContent = 'Screen connected'; $('connection').className = 'ok'; };
  ws.onmessage = (e) => { const data = JSON.parse(e.data); if (data.incidents) render(data); };
  ws.onclose = () => { $('connection').textContent = 'SCREEN OFFLINE · showing last received data'; $('connection').className = 'bad'; setTimeout(connect, 1000); };
}
function tickClocks() {
  document.querySelectorAll('b[data-arrival]').forEach((el) => { el.textContent = countdown(Number(el.dataset.arrival)); });
  document.querySelectorAll('b[data-clock]').forEach((el) => {
    const elapsed = observedElapsed(el.dataset.since);
    if (elapsed !== null) el.textContent = `${el.dataset.clock} · ${elapsed} ago`;
  });
}
setInterval(() => { contact(); tickClocks(); if (lastView && selected && highlights[selected]?.until <= Date.now()) { delete highlights[selected]; render(lastView); } }, 1000);
// Clearing the board takes two presses: the first asks, the second clears (it resets after a few seconds).
let clearArmed = null;
$('clear-board').onclick = async () => {
  const b = $('clear-board');
  if (!clearArmed) { b.textContent = 'Press again to clear every patient'; b.classList.add('armed'); clearArmed = setTimeout(() => { clearArmed = null; b.textContent = 'Clear board'; b.classList.remove('armed'); }, 4000); return; }
  clearTimeout(clearArmed); clearArmed = null; b.textContent = 'Clear board'; b.classList.remove('armed');
  manualSelection = false;
  try { const r = await fetch('/board/clear', { method: 'POST' }); if (!r.ok) throw new Error(); } catch { window.alert('The board was not cleared. Check the ED receiver.'); }
};
connect();
