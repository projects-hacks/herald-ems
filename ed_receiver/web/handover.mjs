import { esc, hhmm } from './view.mjs';

/** The first acknowledgement this screen recorded at or after the final packet arrived (one clock: this screen's). */
export function receivedAfterHandover(incident) {
  const handover = incident.handover;
  if (!handover) return null;
  return (incident.acknowledgements ?? []).find((ack) => ack.status === 'received' && ack.at >= handover.arrived_at) ?? null;
}

/** Who told us what, from the final packet: [{who, items}] in the vehicle's reading order (people other than the crew
 *  first, then the patient monitor, then the crew). An older vehicle does not send it: nothing is shown then. */
export function informantRows(handover) {
  return (Array.isArray(handover?.informants) ? handover.informants : [])
    .filter((row) => row && typeof row.who === 'string' && row.who.trim())
    .map((row) => ({ who: row.who.charAt(0).toUpperCase() + row.who.slice(1), items: (Array.isArray(row.items) ? row.items : []).filter(Boolean) }));
}

/** The vehicle's final packet: the handoff report frozen when the medic handed the patient over. */
export function renderHandover(incident) {
  const handover = incident.handover;
  if (!handover) return '';
  const received = receivedAfterHandover(incident);
  const sections = (handover.sections ?? []).filter((section) => (section.lines ?? []).length);
  const gaps = (handover.not_yet_known ?? []).filter(Boolean);
  const who = informantRows(handover);
  return `<section class="card handover" aria-label="Final handoff report">
    <div class="handover-head"><h2><span aria-hidden="true">✓</span> Handed over ${esc(hhmm(handover.at))} · final report</h2>
    ${received ? `<p class="handover-received" role="status"><span aria-hidden="true">✓</span> Received ${esc(hhmm(received.at))}</p>`
      : '<button id="ack-handover" class="handover-ack">Received</button>'}</div>
    ${handover.title ? `<p class="muted">${esc(handover.title)}</p>` : ''}
    ${sections.map((section) => `<section><h3>${esc(section.label)}</h3><ul>${section.lines.map((line) => `<li>${esc(line)}</li>`).join('')}</ul></section>`).join('')}
    ${who.length ? `<section class="handover-who" aria-labelledby="handover-who-h"><h3 id="handover-who-h">Who told us</h3><ul>${who.map((row) =>
      `<li><b>${esc(row.who)}</b><span>${esc(row.items.join(', ') || 'no items listed')}</span></li>`).join('')}</ul></section>` : ''}
    ${gaps.length ? `<p class="muted">Not yet known: ${esc(gaps.join(' · '))}</p>` : ''}</section>`;
}
