import { expect, it } from 'vitest';
import { replaySteps } from './replay';

it('groups relations by their earliest valid supporting event', () => {
	const edges = [
		{ key: 'later', event_ids: [2, 3] },
		{ key: 'earlier', event_ids: [2, 1] },
		{ key: 'same-time', event_ids: [1] },
		{ key: 'undated', event_ids: [3, 9] }
	];
	const events = [
		{ id: 1, date: '2026-11-01T01:00:00Z' },
		{ id: 2, date: '2026-11-01T02:00:00Z' },
		{ id: 3, date: 'invalid' }
	];
	expect(replaySteps(edges, events)).toEqual([
		{ at: Date.parse(events[0].date), keys: ['earlier', 'same-time'] },
		{ at: Date.parse(events[1].date), keys: ['later'] }
	]);
});
