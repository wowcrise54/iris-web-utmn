// Browser error reports may only reach the operator-configured HTTPS ingest service.
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { request as httpsRequest } from 'node:https';
import { lookup } from 'node:dns/promises';
import { BlockList, isIP } from 'node:net';

const MAX_ENVELOPE_BYTES = 1024 * 1024;
const MAX_RESPONSE_BYTES = 64 * 1024;
const TIMEOUT_MS = 10_000;

function parseDsn(value: unknown) {
	if (typeof value !== 'string') return null;
	try {
		const url = new URL(value);
		const rawPath = value.match(/^https:\/\/[^/?#]+(\/[^?#]*)?$/i)?.[1];
		const path = url.pathname.match(/^(.*)\/([0-9]+)$/);
		if (
			url.protocol !== 'https:' ||
			!/^[a-zA-Z0-9_-]+$/.test(url.username) ||
			url.password ||
			url.search ||
			url.hash ||
			!path ||
			rawPath !== url.pathname
		)
			return null;
		return {
			dsn: url.href,
			publicKey: url.username,
			url: new URL(`${url.origin}${path[1]}/api/${path[2]}/envelope/`)
		};
	} catch {
		return null;
	}
}

const nonPublic = new BlockList();
for (const [address, prefix] of [
	['0.0.0.0', 8],
	['10.0.0.0', 8],
	['100.64.0.0', 10],
	['127.0.0.0', 8],
	['169.254.0.0', 16],
	['172.16.0.0', 12],
	['192.0.0.0', 24],
	['192.0.2.0', 24],
	['192.88.99.0', 24],
	['192.168.0.0', 16],
	['198.18.0.0', 15],
	['198.51.100.0', 24],
	['203.0.113.0', 24],
	['224.0.0.0', 3]
] as const)
	nonPublic.addSubnet(address, prefix, 'ipv4');
const globalV6 = new BlockList();
globalV6.addSubnet('2000::', 3, 'ipv6');
// Special-purpose, documentation and transition ranges are not public ingest destinations.
for (const [address, prefix] of [
	['2001::', 23],
	['2001:db8::', 32],
	['2002::', 16],
	['3fff::', 20]
] as const)
	nonPublic.addSubnet(address, prefix, 'ipv6');

function isPublicAddress(address: string): boolean {
	const family = isIP(address);
	if (family === 4) return !nonPublic.check(address, 'ipv4');
	return family === 6 && globalV6.check(address, 'ipv6') && !nonPublic.check(address, 'ipv6');
}

async function readEnvelope(request: Request): Promise<Buffer> {
	if (Number(request.headers.get('content-length')) > MAX_ENVELOPE_BYTES) {
		throw new RangeError('envelope too large');
	}
	const reader = request.body?.getReader();
	if (!reader) return Buffer.alloc(0);
	let timer: ReturnType<typeof setTimeout>;
	const timeout = new Promise<never>((_, reject) => {
		timer = setTimeout(() => {
			reject(new Error('envelope read timed out'));
			void reader.cancel().catch(() => {});
		}, TIMEOUT_MS);
	});
	try {
		return await Promise.race([
			timeout,
			(async () => {
				const chunks: Buffer[] = [];
				let size = 0;
				while (true) {
					const { done, value } = await reader.read();
					if (done) break;
					size += value.byteLength;
					if (size > MAX_ENVELOPE_BYTES) {
						void reader.cancel().catch(() => {});
						throw new RangeError('envelope too large');
					}
					chunks.push(Buffer.from(value));
				}
				return Buffer.concat(chunks);
			})()
		]);
	} finally {
		clearTimeout(timer!);
		reader.releaseLock();
	}
}

function forwardEnvelope(target: NonNullable<ReturnType<typeof parseDsn>>, body: Buffer) {
	return new Promise<{ status: number; contentType: string; body: Buffer }>((resolve, reject) => {
		const allowPrivate = env.IRIS_UI_ENVELOPE_ALLOW_PRIVATE === '1';
		const hostname = target.url.hostname.replace(/^\[|\]$/g, '');
		if (isIP(hostname) && !allowPrivate && !isPublicAddress(hostname)) {
			reject(new Error('non-public ingest address'));
			return;
		}
		const req = httpsRequest(
			{
				method: 'POST',
				hostname,
				port: target.url.port || 443,
				path: target.url.pathname,
				rejectUnauthorized: env.IRIS_UI_ENVELOPE_INSECURE_TLS !== '1',
				// Validate at the actual socket lookup: no second resolution or DNS rebinding window.
				lookup: (host, options, callback) => {
					lookup(host, { all: true })
						.then((addresses) => {
							if (
								!addresses.length ||
								(!allowPrivate && addresses.some((a) => !isPublicAddress(a.address)))
							) {
								throw new Error('non-public ingest address');
							}
							const address = addresses.find((a) => !options.family || a.family === options.family);
							if (!address) throw new Error('no matching ingest address');
							if (options.all) callback(null, [address]);
							else callback(null, address.address, address.family);
						})
						.catch((err) => callback(err, '', 0));
				},
				headers: {
					'Content-Type': 'application/x-sentry-envelope',
					'Content-Length': String(body.length),
					'X-Sentry-Auth': `Sentry sentry_version=7, sentry_client=iris-envelope-tunnel/1, sentry_key=${target.publicKey}`
				}
			},
			(res) => {
				const chunks: Buffer[] = [];
				let size = 0;
				res.on('error', reject);
				res.on('aborted', () => req.destroy(new Error('ingest response aborted')));
				res.on('data', (chunk: Buffer) => {
					size += chunk.length;
					if (size > MAX_RESPONSE_BYTES) req.destroy(new Error('ingest response too large'));
					else chunks.push(chunk);
				});
				res.on('end', () => {
					clearTimeout(timer);
					resolve({
						status: res.statusCode ?? 502,
						contentType: res.headers['content-type'] ?? 'application/json',
						body: Buffer.concat(chunks)
					});
				});
			}
		);
		const timer = setTimeout(() => req.destroy(new Error('ingest timed out')), TIMEOUT_MS);
		req.on('error', (err) => {
			clearTimeout(timer);
			reject(err);
		});
		req.on('close', () => clearTimeout(timer));
		req.end(body);
	});
}

export const POST: RequestHandler = async ({ request }) => {
	const target = parseDsn(env.IRIS_UI_SENTRY_DSN);
	if (!target) return new Response('ingest not configured', { status: 503 });
	let body: Buffer;
	try {
		body = await readEnvelope(request);
	} catch (err) {
		return new Response('invalid envelope body', { status: err instanceof RangeError ? 413 : 408 });
	}
	const newline = body.indexOf(10);
	if (newline === -1) return new Response('bad envelope', { status: 400 });
	let header: unknown;
	try {
		header = JSON.parse(body.subarray(0, newline).toString('utf8'));
	} catch {
		return new Response('bad envelope header', { status: 400 });
	}
	if (
		!header ||
		typeof header !== 'object' ||
		!('dsn' in header) ||
		typeof header.dsn !== 'string' ||
		!header.dsn
	) {
		return new Response('missing dsn', { status: 400 });
	}
	const submitted = parseDsn(header.dsn);
	if (!submitted || submitted.dsn !== target.dsn)
		return new Response('dsn not allowed', { status: 403 });
	try {
		const upstream = await forwardEnvelope(target, body);
		return new Response(
			[204, 205, 304].includes(upstream.status) ? null : new Uint8Array(upstream.body),
			{
				status: upstream.status,
				headers: { 'Content-Type': upstream.contentType }
			}
		);
	} catch {
		return new Response('ingest unavailable', { status: 502 });
	}
};
