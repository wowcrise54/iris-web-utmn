import { describe, expect, it } from 'vitest';
import { readOpenCTI, readOpenCTISummary, safeHttpUrl } from '../opencti';

describe('OpenCTI presentation', () => {
	it('accepts provider data and rejects malformed payloads', () => {
		expect(readOpenCTI({ vt: {} })).toBeNull();
		expect(readOpenCTI({ opencti: 'bad' })).toBeNull();
		expect(
			readOpenCTI({
				opencti: { status: 'matched', observables: [null, { id: 'one' }], indicators: [] }
			})?.observables
		).toHaveLength(1);
	});
	it('reads only the module-owned summary attribute', () => {
		expect(readOpenCTISummary({ __iris_opencti: { value: '{bad' } })).toBeNull();
		expect(
			readOpenCTISummary({
				__iris_opencti: {
					value: JSON.stringify({ schema_version: 1, total: 2, counts: { matched: 1 }, iocs: [] })
				}
			})?.total
		).toBe(2);
	});
	it('permits only HTTP links from remote enrichment', () => {
		expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
		expect(safeHttpUrl('data:text/html,bad')).toBeNull();
		expect(safeHttpUrl('https://cti.example/dashboard')).toBe('https://cti.example/dashboard');
	});
});
