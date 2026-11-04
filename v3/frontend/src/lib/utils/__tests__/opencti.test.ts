import { afterEach, describe, expect, it, vi } from 'vitest';
import { readOpenCTI, readOpenCTISummary, safeHttpUrl, startOpenCTIRefresh } from '../opencti';

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('OpenCTI result refresh', () => {
	it('waits for the response before polling again and stops after leaving the view', async () => {
		vi.useFakeTimers();
		let resolve!: () => void;
		const refresh = vi.fn(
			() =>
				new Promise<void>((done) => {
					resolve = done;
				})
		);
		const stop = startOpenCTIRefresh(refresh);
		await vi.advanceTimersByTimeAsync(1000);
		expect(refresh).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(15000);
		expect(refresh).toHaveBeenCalledTimes(1);
		stop();
		resolve();
		await vi.advanceTimersByTimeAsync(10000);
		expect(refresh).toHaveBeenCalledTimes(1);
	});
	it('pauses in a hidden tab and retries after a failed refresh', async () => {
		vi.useFakeTimers();
		const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
		const refresh = vi
			.fn()
			.mockRejectedValueOnce(new Error('offline'))
			.mockResolvedValue(undefined);
		const stop = startOpenCTIRefresh(refresh);
		await vi.advanceTimersByTimeAsync(1000);
		expect(refresh).not.toHaveBeenCalled();
		hidden.mockReturnValue(false);
		await vi.advanceTimersByTimeAsync(10000);
		expect(refresh).toHaveBeenCalledTimes(2);
		stop();
	});
});

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
