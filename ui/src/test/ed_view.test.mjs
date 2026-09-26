import { expect, it } from 'vitest';
import { newestPatient, fieldKeys, isNewField, formatValue, esc, observedElapsed, hhmm } from '../../../ed_receiver/web/view.mjs';
import { journeyGroups, renderJourney } from '../../../ed_receiver/web/journey.mjs';
it('opens newest received incident and retains unknown keys', () => {
  const incidents = { old: { first_at: '2026-09-24' }, newest: { first_at: '2026-09-25' } };
  expect(newestPatient(incidents)).toBe('newest');
  expect(fieldKeys({ fields: { 'new.key': { v: 1 } } })).toContain('new.key');
});
it('compares new fields against the selected patient sequence, not a map', () => {
  expect(isNewField({ seq: 3 }, 2)).toBe(true); expect(isNewField({ seq: 2 }, 2)).toBe(false);
  expect(formatValue({ drug: 'naloxone', dose: .4 })).not.toContain('[object');
  expect(esc('<script>')).toBe('&lt;script&gt;');
});
it('uses the vehicle timestamp for LKW instead of guessing the receiving browser timezone', () => {
  expect(observedElapsed('2026-09-25T13:04:00-07:00', Date.parse('2026-09-25T21:16:00Z'))).toBe('1 h 12 m');
  expect(observedElapsed('13:04')).toBeNull();
  expect(observedElapsed('2026-09-25T13:04:00')).toBeNull();
});
it('shows only received journey points with units, times, and escaped care events', () => {
  const timeline = [
    { k: 'vitals.sbp', v: 132, t: '2026-09-25T17:00:20Z', o: '2026-09-25T17:00:00Z' },
    { k: 'vitals.sbp', v: 88, t: '2026-09-25T17:02:20Z', o: '2026-09-25T17:02:00Z' },
    { k: 'meds.given', v: { drug: '<script>' }, t: 'invalid' },
  ];
  expect(journeyGroups(timeline).vitals).toHaveLength(1);
  const html = renderJourney({ timeline }, { 'vitals.sbp': { label: 'Systolic BP', unit: 'mmHg' } });
  expect(html).toContain('132 mmHg'); expect(html).toContain(hhmm('2026-09-25T17:00:00Z'));   // the observed time, local 24-hour
  expect(html).not.toContain('<script>'); expect(html).toContain('Time unavailable');
});
it('shows the route arrival time as clock time and leaves other text alone', () => {
  expect(formatValue('2026-09-26T01:40:00Z')).toBe(hhmm('2026-09-26T01:40:00Z'));
  expect(formatValue('13:15')).toBe('13:15');
  expect(formatValue('Patient refused transport')).toBe('Patient refused transport');
});
