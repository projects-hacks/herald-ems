import { esc, hhmm } from './view.mjs';

/** The first acknowledgement this screen recorded at or after the final packet arrived (one clock: this screen's). */
export function receivedAfterHandover(incident) {
  const handover = incident.handover;
  if (!handover) return null;
  return (incident.acknowledgements ?? []).find((ack) => ack.status === 'received' && ack.at >= handover.arrived_at) ?? null;
}

/** The vehicle's final packet: the handoff report frozen when the medic handed the patient over. */
export function renderHandover(incident) {
  const handover = incident.handover;
  if (!handover) return '';
  const received = receivedAfterHandover(incident);
  const sections = (handover.sections ?? []).filter((section) => (section.lines ?? []).length);
  const gaps = (handover.not_yet_known ?? []).filter(Boolean);
  return `<section class="card handover" aria-label="Final handoff report">
    <div class="handover-head"><h2><span aria-hidden="true">✓</span> Handed over ${esc(hhmm(handover.at))} · final report</h2>
    ${received ? `<p class="handover-received" role="status"><span aria-hidden="true">✓</span> Received ${esc(hhmm(received.at))}</p>`
      : '<button id="ack-handover" class="handover-ack">Received</button>'}</div>
    ${handover.title ? `<p class="muted">${esc(handover.title)}</p>` : ''}
    ${sections.map((section) => `<section><h3>${esc(section.label)}</h3><ul>${section.lines.map((line) => `<li>${esc(line)}</li>`).join('')}</ul></section>`).join('')}
    ${gaps.length ? `<p class="muted">Not yet known: ${esc(gaps.join(' · '))}</p>` : ''}</section>`;
}
