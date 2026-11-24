import { expect, it } from 'vitest';
import { parseGraphSuggestions } from './suggestions';

it('accepts only supported links between known graph nodes', () => {
	const suggestion = {
		source: 'asset:1',
		target: 'asset:2',
		relation: 'related_to',
		directed: false,
		event_ids: [3, 3],
		rationale: 'Both assets appear in event 3.'
	};
	const input = JSON.stringify([
		suggestion,
		{ ...suggestion, target: 'asset:3' },
		{ ...suggestion, event_ids: [] },
		{ ...suggestion, relation: 'unknown' }
	]);
	expect(
		parseGraphSuggestions(input, new Set(['asset:1', 'asset:2']), new Set(['related_to']))
	).toEqual([{ ...suggestion, event_ids: [3] }]);
});

it('supports a JSON code fence and rejects non-JSON output', () => {
	const fence = String.fromCharCode(96).repeat(3);
	const row = {
		source: 'asset:1',
		target: 'asset:2',
		relation: 'related_to',
		directed: true,
		event_ids: [3],
		rationale: 'Evidence'
	};
	const keys = new Set(['asset:1', 'asset:2']);
	const relations = new Set(['related_to']);
	const json = JSON.stringify([row]);
	expect(parseGraphSuggestions(fence + 'json\n' + json + '\n' + fence, keys, relations)).toEqual([
		row
	]);
	expect(parseGraphSuggestions('Proposed: ' + json, keys, relations)).toEqual([]);
});
