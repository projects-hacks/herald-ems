import { expect, it } from 'vitest';
import { newestPatient, fieldKeys, isNewField, formatValue, esc, observedElapsed, hhmm, openChecklists, alertBadges, ageSex,
  vitalTile, sparkline, careText, careEvents } from '../../../ed_receiver/web/view.mjs';
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
const alerts = [
  { checklist: 'stemi', text: 'STEMI ALERT', tone: 'critical', score: 'score.stemi_700a08', readiness_label: 'STEMI alert' },
  { checklist: 'sepsis', text: 'SEPSIS ALERT', tone: 'warning', score: 'score.sepsis_700a04', readiness_label: 'Suspected sepsis' },
  { checklist: 'stroke', text: 'STROKE ALERT', tone: 'critical', readiness_label: 'Stroke alert' },
];
const scoreKeys = { 'score.stemi_700a08': { not_met: 'not met' }, 'score.sepsis_700a04': { not_met: 'not met' } };
it('shows an alert badge only for an open checklist or a met criteria score the vehicle sent', () => {
  expect(openChecklists('STEMI alert 3/5; Stroke alert 7/7 ready; garbage')).toEqual([
    { label: 'STEMI alert', done: 3, total: 5, ready: false }, { label: 'Stroke alert', done: 7, total: 7, ready: true }]);
  expect(alertBadges({}, alerts, scoreKeys)).toEqual([]);
  const open = alertBadges({ 'alert.readiness': { v: 'STEMI alert 5/5 ready' } }, alerts, scoreKeys);
  expect(open.map((b) => b.text)).toEqual(['STEMI ALERT']); expect(open[0].detail).toBe('pre-alert 5/5 ready');
  const met = alertBadges({ 'score.stemi_700a08': { v: 'met (STEMI interpretation documented)' }, 'score.sepsis_700a04': { v: 'not met' } }, alerts, scoreKeys);
  expect(met).toEqual([{ text: 'STEMI ALERT', tone: 'critical', detail: 'criteria met' }]);
});
it('writes age and sex from received fields only', () => {
  const header = { age: 'patient.age', sex: 'patient.sex' };
  expect(ageSex({ 'patient.age': { v: 62 }, 'patient.sex': { v: 'male' } }, header)).toBe('62 M');
  expect(ageSex({ 'patient.sex': { v: 'female' } }, header)).toBe('F');
  expect(ageSex({}, header)).toBeNull();
});
it('builds a vital tile from received values, with its trend, severity and a missing state', () => {
  const incident = {
    fields: { 'vitals.sbp': { v: 92, t: '2026-09-25T17:03:00Z' }, 'vitals.dbp': { v: 56, t: '2026-09-25T17:02:00Z' } },
    history: { 'vitals.sbp': [{ v: 146, t: 'a' }, { v: 118, t: 'b' }, { v: 92, t: 'c' }] }, severity: { 'vitals.sbp': 'abnormal' },
  };
  const keys = { 'vitals.sbp': { unit: 'mmHg' } };
  const tile = vitalTile({ short: 'BP', keys: ['vitals.sbp', 'vitals.dbp'], join: '/' }, incident, keys);
  expect(tile).toMatchObject({ value: '92/56', unit: 'mmHg', severity: 'abnormal', direction: -1, at: '2026-09-25T17:03:00Z' });
  expect(tile.previous.v).toBe(118);
  expect(vitalTile({ short: 'HR', keys: ['vitals.hr'] }, incident, keys)).toEqual({ short: 'HR', missing: true });
  expect(sparkline([{ v: 1 }])).toBe('');
  expect(sparkline([{ v: 10 }, { v: 20 }], 100, 10)).toBe('0,10 100,0');
});
it('lists care events with the best time the received data holds, oldest first', () => {
  const asa = { drug: 'aspirin', dose: 324, unit: 'mg', route: 'PO' }, defib = { procedure: 'defibrillation', detail: '200 J' };
  expect(careText(asa)).toBe('aspirin 324 mg PO');
  expect(careText({ drug: 'heparin', before_arrival: true })).toBe('heparin before EMS arrival');
  const incident = {
    fields: { 'meds.given': { v: [asa], t: '2026-09-25T17:10:00Z' }, 'procedures.done': { v: [defib], t: '2026-09-25T17:10:00Z' } },
    history: { 'procedures.done': [{ v: [defib], t: '2026-09-25T17:09:00Z' }] },
    timeline: [{ k: 'meds.given', v: asa, t: '2026-09-25T17:01:00Z', o: '2026-09-25T17:00:00Z' }],
  };
  const events = careEvents(incident, ['meds.given', 'procedures.done']);
  expect(events.map((e) => [e.text, e.time, e.source])).toEqual([
    ['aspirin 324 mg PO', hhmm('2026-09-25T17:00:00Z'), 'recorded'],
    ['defibrillation 200 J', hhmm('2026-09-25T17:09:00Z'), 'received']]);
});
