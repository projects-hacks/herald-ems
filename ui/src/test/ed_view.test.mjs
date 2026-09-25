import { expect, it } from 'vitest';
import { newestPatient, fieldKeys, isNewField, formatValue, esc } from '../../../ed_receiver/web/view.mjs';
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
