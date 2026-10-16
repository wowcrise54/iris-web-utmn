// @vitest-environment node
import { EventEmitter } from 'node:events';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
	env: {} as Record<string, string>,
	addresses: [{ address: '93.184.216.34', family: 4 }],
	response: 'accepted',
	stalled: false,
	destinations: [] as string[],
	path: '',
	port: '' as string | number,
	body: Buffer.alloc(0) as Buffer,
	pinned: [] as unknown[],
	dnsStalled: false,
	dnsCalls: 0
}));
vi.mock('$env/dynamic/private', () => ({ env: state.env }));
vi.mock('node:dns/promises', () => ({
	lookup: async () => {
		state.dnsCalls++;
		return state.dnsStalled ? new Promise(() => {}) : state.addresses;
	}
}));
vi.mock('node:http', async () => ({ request: (await import('node:https')).request }));
vi.mock('node:https', () => ({
	request: (options: any, onResponse: any) => {
		const req = new EventEmitter() as any;
		req.write = () => {};
		req.destroy = (error: Error) => {
			req.emit('error', error);
			return req;
		};
		req.end = (body: Buffer) => {
			state.path = options.path;
			state.port = options.port;
			state.body = body;
			// Exercise the lookup passed to the real transport, including address validation.
			if (!options.lookup) state.destinations.push(options.hostname);
			const respond = () => {
				if (state.stalled) return;
				const res = new EventEmitter() as any;
				res.statusCode = 202;
				res.headers = { 'content-type': 'text/plain' };
				res.destroy = (error: Error) => res.emit('error', error);
				onResponse(res);
				res.emit('data', Buffer.from(state.response));
				res.emit('end');
			};
			queueMicrotask(() =>
				options.lookup
					? options.lookup(options.hostname, { all: true }, (err: Error, addresses: unknown) => {
							if (err) req.emit('error', err);
							else {
								state.pinned.push(addresses);
								state.destinations.push(options.hostname);
								respond();
							}
						})
					: respond()
			);
		};
		return req;
	}
}));
const { POST } = await import('../routes/monitoring/envelope/+server');
const send = (dsn: unknown = 'https://key@errors.example/42', extra = '') =>
	POST({
		request: new Request('https://iris.example/monitoring/envelope', {
			method: 'POST',
			body: JSON.stringify({ dsn }) + '\n' + extra
		})
	} as never);

beforeEach(() => {
	for (const key of Object.keys(state.env)) delete state.env[key];
	state.env.IRIS_UI_SENTRY_DSN = 'https://key@errors.example/42';
	state.addresses = [{ address: '93.184.216.34', family: 4 }];
	state.response = 'accepted';
	state.stalled = false;
	state.destinations = [];
	state.dnsStalled = false;
	state.dnsCalls = 0;
	state.pinned = [];
});

describe('Sentry tunnel boundary', () => {
	it('fails closed when the trusted destination is absent or invalid', async () => {
		delete state.env.IRIS_UI_SENTRY_DSN;
		expect((await send()).status).toBe(503);
		state.env.IRIS_UI_SENTRY_DSN = 'not a DSN';
		expect((await send()).status).toBe(503);
		expect(state.destinations).toEqual([]);
	});
	it.each([
		'https://key@other.example/42',
		'https://other@errors.example/42',
		'https://key@errors.example/43',
		'http://key@errors.example/42',
		'ftp://key@errors.example/42',
		'https://key@errors.example/%34%32',
		'https://key@errors.example/a/../../42',
		'https://key@errors.example/42?x=1',
		'https://key@errors.example/42#x',
		'https://key:secret@errors.example/42',
		'https://key@errors.example:8443/42'
	])('rejects a different host, key, project or scheme: %s', async (dsn) => {
		expect((await send(dsn)).status).toBe(403);
		expect(state.destinations).toEqual([]);
	});
	it('forwards a configured HTTPS envelope', async () => {
		const response = await send();
		expect(response.status).toBe(202);
		expect(await response.text()).toBe('accepted');
		expect(state.destinations).toEqual(['errors.example']);
	});
	it('preserves the configured path prefix, port and underscore key', async () => {
		state.env.IRIS_UI_SENTRY_DSN = 'https://public_key@errors.example:8443/sentry/42';
		expect((await send(state.env.IRIS_UI_SENTRY_DSN)).status).toBe(202);
		expect(state.path).toBe('/sentry/api/42/envelope/');
		expect(state.port).toBe('8443');
	});
	it('preserves binary payload bytes and pins the validated DNS result', async () => {
		const body = Buffer.concat([
			Buffer.from('{"dsn":"https://key@errors.example/42"}\n'),
			Buffer.from([0xff, 0x00, 0x89])
		]);
		const response = await POST({
			request: new Request('https://iris.example/monitoring/envelope', {
				method: 'POST',
				body
			})
		} as never);
		expect(response.status).toBe(202);
		expect(state.body).toEqual(body);
		expect(state.pinned).toEqual([[{ address: '93.184.216.34', family: 4 }]]);
		expect(state.dnsCalls).toBe(1);
	});
	it('rejects mixed public/private DNS answers', async () => {
		state.addresses.push({ address: '::1', family: 6 });
		expect((await send()).status).toBe(502);
		expect(state.destinations).toEqual([]);
	});
	it.each(['127.1', '2130706433', '0x7f000001', '[::ffff:127.0.0.1]'])(
		'blocks configured private IP literals even when DNS would return public: %s',
		async (host) => {
			state.env.IRIS_UI_SENTRY_DSN = `https://key@${host}/42`;
			expect((await send(state.env.IRIS_UI_SENTRY_DSN)).status).toBe(502);
			expect(state.destinations).toEqual([]);
		}
	);
	it.each([
		'127.0.0.1',
		'10.0.0.1',
		'169.254.169.254',
		'100.64.0.1',
		'192.168.1.1',
		'::1',
		'fe80::1',
		'fc00::1',
		'::ffff:127.0.0.1'
	])('blocks non-public DNS results before connecting: %s', async (address) => {
		state.addresses = [{ address, family: address.includes(':') ? 6 : 4 }];
		expect((await send()).status).toBe(502);
		expect(state.destinations).toEqual([]);
	});
	it('allows a private configured deployment only with explicit opt-in', async () => {
		state.env.IRIS_UI_ENVELOPE_ALLOW_PRIVATE = '1';
		state.addresses = [{ address: '10.0.0.1', family: 4 }];
		expect((await send()).status).toBe(202);
		expect((await send('https://key@other.example/42')).status).toBe(403);
	});
	it('bounds incoming bytes even without Content-Length', async () => {
		expect((await send(undefined, 'x'.repeat(1024 * 1024))).status).toBe(413);
		expect(state.destinations).toEqual([]);
	});
	it('bounds upstream response bytes', async () => {
		state.response = 'x'.repeat(64 * 1024 + 1);
		expect((await send()).status).toBe(502);
	});
	it('bounds the total upstream wait', async () => {
		vi.useFakeTimers();
		state.stalled = true;
		try {
			const pending = send();
			await vi.advanceTimersByTimeAsync(10_001);
			expect((await pending).status).toBe(502);
		} finally {
			vi.useRealTimers();
		}
	});
	it('bounds a stalled DNS resolution before connection', async () => {
		vi.useFakeTimers();
		state.dnsStalled = true;
		try {
			const pending = send();
			await vi.advanceTimersByTimeAsync(10_001);
			expect((await pending).status).toBe(502);
			expect(state.destinations).toEqual([]);
		} finally {
			vi.useRealTimers();
		}
	});
	it.each([null, 123, {}, ''])('rejects malformed DSN values: %s', async (dsn) => {
		expect((await send(dsn)).status).toBe(400);
	});
});
