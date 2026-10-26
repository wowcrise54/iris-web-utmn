import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import {
	createLogger,
	sanitize,
	createClientTransport,
	configureServerLogging,
	logger
} from '../logger';

vi.mock('$app/environment', () => ({ browser: false, dev: false, building: false }));

describe('unified logging', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	it('applies parent prefixes with exact overrides winning on the server', () => {
		const output: string[] = [];
		vi.spyOn(console, 'log').mockImplementation((row) => output.push(row));
		configureServerLogging({ IRIS_LOG_LEVELS: '{"iris":"DEBUG"}' }, () => ({}));
		logger.debug('parent_enabled');
		configureServerLogging(
			{ IRIS_LOG_LEVELS: '{"iris":"DEBUG","iris.frontend":"ERROR"}' },
			() => ({})
		);
		logger.info('exact_suppressed');
		expect(output.map((row) => JSON.parse(row).event)).toEqual(['parent_enabled']);
	});

	it('drops unauthenticated and previous-session browser events', async () => {
		let session: number | null = null;
		const batches: { events: { message: string }[] }[] = [];
		const transport = createClientTransport(
			async (body) => {
				batches.push(body);
			},
			() => session
		);
		transport.enqueue({ level: 'ERROR', event: 'failed', message: 'anonymous' });
		session = 1;
		transport.enqueue({ level: 'ERROR', event: 'failed', message: 'user_a' });
		session = null;
		session = 2;
		transport.enqueue({ level: 'ERROR', event: 'failed', message: 'user_b' });
		await transport.flush();
		expect(batches.flatMap((body) => body.events.map((event) => event.message))).toEqual([
			'user_b'
		]);
		transport.stop();
	});

	it('filters levels and never outputs credentials, bodies or exception values', () => {
		const rows: string[] = [];
		const log = createLogger({ level: 'INFO', sink: (row) => rows.push(JSON.stringify(row)) });
		log.debug('hidden');
		log.info('loaded', { count: 3, password: 'inert-secret', body: 'private-body' });
		log.error('failed', new Error('private-exception'));
		expect(rows).toHaveLength(2);
		expect(rows.join('')).not.toMatch(/inert-secret|private-body|private-exception/);
		expect(rows[0]).toContain('"count":3');
	});

	it('handles cycles and strips URLs and bearer credentials', () => {
		const cyclic: Record<string, unknown> = { token: 'inert-secret' };
		cyclic.self = cyclic;
		expect(() => sanitize(cyclic)).not.toThrow();
		expect(
			JSON.stringify(sanitize('Bearer inert-token https://host/path?token=inert-secret'))
		).not.toMatch(/inert-token|inert-secret/);
		expect(JSON.stringify(sanitize('{"password": "inert quoted secret"}'))).not.toContain(
			'inert quoted secret'
		);
	});

	it('bounds batches and queue, drops failed sends without recursion', async () => {
		const batches: unknown[] = [];
		const transport = createClientTransport(async (body) => {
			batches.push(body);
			throw new Error('offline');
		});
		for (let i = 0; i < 500; i++)
			transport.enqueue({ level: 'ERROR', event: 'failed', message: 'failed' });
		await transport.flush();
		expect((batches[0] as { events: unknown[] }).events).toHaveLength(20);
		await vi.advanceTimersByTimeAsync(60000);
		expect(batches.length).toBeLessThanOrEqual(3);
		transport.stop();
	});

	it('only forwards warnings and higher with a bounded allowlisted payload', () => {
		const events: unknown[] = [];
		const log = createLogger({
			level: 'TRACE',
			sink: () => {},
			forward: (event) => events.push(event)
		});
		log.debug('debug');
		log.info('info');
		log.warn('load failed', { user_id: 999, body: 'private-body', request_id: 'req-one' });
		expect(events).toEqual([expect.objectContaining({ level: 'WARNING', request_id: 'req-one' })]);
		expect(JSON.stringify(events)).not.toMatch(/999|private-body|user_id/);
	});
});
