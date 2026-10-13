import { describe, it, expect } from 'vitest';
import { toLocalInput, fromLocalInput, cardPayload } from '../incident-card';
describe('incident card draft', () => {
	it('shows UTC in chosen timezone', () =>
		expect(toLocalInput('2026-10-13T00:00:00Z', 'Asia/Yekaterinburg')).toBe('2026-10-13T05:00:00'));
	it('converts summer DST local time to UTC', () =>
		expect(fromLocalInput('2026-07-01T12:00:00', 'Europe/Paris')).toBe('2026-07-01T10:00:00.000Z'));
	it('rejects nonexistent DST local time', () =>
		expect(() => fromLocalInput('2026-03-29T02:30:00', 'Europe/Paris')).toThrow());
	it('sends only editable draft properties', () =>
		expect(
			cardPayload({
				schema_version: 1,
				revision: 3,
				fields: { title: { value: 'X', mode: 'manual', source: 'case', status: 'manual' } },
				selections: {},
				meta: { author: 'A' }
			} as any)
		).toEqual({
			schema_version: 1,
			revision: 3,
			fields: { title: { value: 'X', mode: 'manual' } },
			selections: {}
		}));
});
