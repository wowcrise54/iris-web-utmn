import { describe, it, expect } from 'vitest';
import { toLocalInput, fromLocalInput, cardPayload, deriveCard } from '../incident-card';
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

describe('live incident calculations', () => {
	it('recalculates importance, automatic priority and finished duration from current fields', () => {
		const fields: any = {
			categories: { value: [2] },
			prioritization_type: { value: 'target' },
			priority_override: { value: 9, mode: 'auto' },
			completed: { value: true },
			occurred_at: { value: '2026-10-20T00:00:00Z' },
			incident_ended_at: { value: '2026-10-20T01:30:00Z' }
		};
		expect(deriveCard(fields)).toEqual({
			importance: 'high',
			priority: 1,
			incident_duration_seconds: 5400
		});
		fields.prioritization_type.value = 'auxiliary';
		expect(deriveCard(fields).priority).toBe(6);
		fields.completed.value = false;
		expect(deriveCard(fields).incident_duration_seconds).toBeNull();
	});
});
