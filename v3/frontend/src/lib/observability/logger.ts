import { browser } from '$app/environment';
import { getLastRequestId } from './request-id-store';

export type Level = 'TRACE' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
const levels: Record<Level, number> = {
	TRACE: 5,
	DEBUG: 10,
	INFO: 20,
	WARNING: 30,
	ERROR: 40,
	CRITICAL: 50
};
type Row = Record<string, unknown>;
export type ClientEvent = {
	level: Level;
	event: string;
	message: string;
	request_id?: string;
	path?: string;
	stack?: string;
};
const sensitive =
	/password|passwd|secret|token|cookie|authorization|credential|api.?key|dsn|body|payload|prompt|response|content|arguments|headers|attachment|evidence|ioc/i;
const metadataKeys = new Set([
	'request_id',
	'task_id',
	'method',
	'path',
	'status',
	'duration_ms',
	'count',
	'stage',
	'result',
	'error_type',
	'namespace'
]);

function text(value: string): string {
	return value
		.slice(0, 8192)
		.replace(/\b(Bearer|Basic)\s+[^\s,;'"\]]+/gi, '$1 [Filtered]')
		.replace(
			/((?:password|passwd|secret|token|cookie|authorization|credential|api[_-]?key|dsn)[\w-]*["']?\s*[:=]\s*)(["'])(.*?)(?:\2|$)/gis,
			'$1[Filtered]'
		)
		.replace(
			/((?:password|passwd|secret|token|cookie|authorization|credential|api[_-]?key|dsn)[\w-]*["']?\s*[:=]\s*)[^\s,;&"']+/gi,
			'$1[Filtered]'
		)
		.replace(/https?:\/\/[^\s<>"']+/g, (url) => {
			try {
				const parsed = new URL(url);
				return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
			} catch {
				return '[Filtered URL]';
			}
		})
		.replace(/[\r\n]/g, ' ')
		.slice(0, 2048);
}

export function sanitize(value: unknown, depth = 0, seen = new WeakSet<object>()): unknown {
	if (depth > 4) return '[truncated]';
	if (typeof value === 'string') return text(value);
	if (value == null || typeof value === 'boolean' || typeof value === 'number') return value;
	if (value instanceof Error) return { error_type: value.name };
	if (typeof value !== 'object') return `[${typeof value}]`;
	if (seen.has(value)) return '[circular]';
	seen.add(value);
	if (Array.isArray(value))
		return value.slice(0, 20).map((entry) => sanitize(entry, depth + 1, seen));
	return Object.fromEntries(
		Object.entries(value)
			.slice(0, 20)
			.map(([key, item]) => [
				key.slice(0, 64),
				sensitive.test(key) ? '[Filtered]' : sanitize(item, depth + 1, seen)
			])
	);
}

function metadata(args: unknown[]): Row {
	const result: Row = {};
	for (const arg of args) {
		if (arg instanceof Error) {
			result.error_type = arg.name;
			continue;
		}
		if (!arg || typeof arg !== 'object' || Array.isArray(arg)) continue;
		for (const [key, value] of Object.entries(arg)) {
			if (metadataKeys.has(key) && ['string', 'number', 'boolean'].includes(typeof value))
				result[key] = key === 'path' ? String(value).split(/[?#]/, 1)[0] : sanitize(value);
		}
	}
	return result;
}

export function createLogger(options: {
	level: Level | (() => Level);
	sink: (row: Row) => void;
	forward?: (event: ClientEvent) => void;
	context?: () => Row;
}) {
	function write(level: Level, message: unknown, ...args: unknown[]) {
		const threshold = typeof options.level === 'function' ? options.level() : options.level;
		if (levels[level] < levels[threshold]) return;
		const label =
			typeof message === 'string'
				? text(message)
				: message instanceof Error
					? message.name
					: 'diagnostic_event';
		const fields = { ...options.context?.(), ...metadata(args) };
		const event = label.replace(/[^a-zA-Z0-9_.:-]+/g, '_').slice(0, 96) || 'diagnostic_event';
		options.sink({
			time: new Date().toISOString(),
			level,
			service: 'frontend',
			logger: 'iris.frontend',
			event,
			message: label,
			...fields
		});
		if (levels[level] >= levels.WARNING && options.forward) {
			const clientEvent: ClientEvent = { level, event, message: label };
			if (
				typeof fields.request_id === 'string' &&
				/^[A-Za-z0-9_.:-]{1,128}$/.test(fields.request_id)
			)
				clientEvent.request_id = fields.request_id;
			if (browser) clientEvent.path = window.location.pathname;
			const error = args.find((arg) => arg instanceof Error) as Error | undefined;
			if (error?.stack)
				clientEvent.stack = error.stack
					.split('\n')
					.filter((line) => /^\s*(at |[^\s@]+@)/.test(line))
					.slice(0, 12)
					.map(text)
					.join('\n')
					.slice(0, 4096);
			options.forward(clientEvent);
		}
	}
	return {
		trace: (message: unknown, ...args: unknown[]) => write('TRACE', message, ...args),
		debug: (message: unknown, ...args: unknown[]) => write('DEBUG', message, ...args),
		info: (message: unknown, ...args: unknown[]) => write('INFO', message, ...args),
		warn: (message: unknown, ...args: unknown[]) => write('WARNING', message, ...args),
		error: (message: unknown, ...args: unknown[]) => write('ERROR', message, ...args),
		critical: (message: unknown, ...args: unknown[]) => write('CRITICAL', message, ...args)
	};
}

export function createClientTransport(
	send: (body: { events: ClientEvent[] }) => Promise<unknown>,
	getSession: () => unknown = () => true
) {
	const queue: { event: ClientEvent; session: unknown }[] = [];
	let timer: ReturnType<typeof setTimeout> | undefined;
	let sending = false;
	let stopped = false;
	let sentAt: number[] = [];
	function schedule() {
		if (!timer && !stopped && queue.length)
			timer = setTimeout(() => {
				timer = undefined;
				void flush();
			}, 5000);
	}
	async function flush() {
		if (stopped || sending || !queue.length) return;
		const session = getSession();
		for (let i = queue.length - 1; i >= 0; i--) {
			if (session == null || queue[i].session !== session) queue.splice(i, 1);
		}
		if (!queue.length) return;
		sentAt = sentAt.filter((time) => time > Date.now() - 60000);
		if (sentAt.length >= 60) {
			schedule();
			return;
		}
		const events: ClientEvent[] = [];
		while (queue.length && events.length < 20 && events.length < 60 - sentAt.length) {
			const next = queue[0].event;
			if (new TextEncoder().encode(JSON.stringify({ events: [...events, next] })).length > 65536)
				break;
			events.push(queue.shift()!.event);
		}
		if (!events.length) {
			queue.shift();
			schedule();
			return;
		}
		sending = true;
		sentAt.push(...events.map(() => Date.now()));
		try {
			await send({ events });
		} catch {
			/* Drop failed batches: no recursion or retry storm. */
		} finally {
			sending = false;
			schedule();
		}
	}
	return {
		enqueue(event: ClientEvent) {
			const session = getSession();
			if (session == null) return;
			if (!stopped && queue.length < 60) {
				queue.push({ event, session });
				schedule();
			}
		},
		flush,
		stop() {
			stopped = true;
			if (timer) clearTimeout(timer);
			queue.length = 0;
		}
	};
}

let transport: ReturnType<typeof createClientTransport> | undefined;
let serverLevel: Level = 'INFO';
let serverContext: () => Row = () => ({});
let serverFormat = 'json';
export function configureServerLogging(
	env: Record<string, string | undefined>,
	context: () => Row
) {
	const level = (env.LOG_LEVEL || 'INFO').toUpperCase();
	let overrides: Record<string, string> = {};
	try {
		overrides = JSON.parse(env.IRIS_LOG_LEVELS || '{}');
		if (
			!overrides ||
			Array.isArray(overrides) ||
			typeof overrides !== 'object' ||
			Object.keys(overrides).length > 100 ||
			Object.entries(overrides).some(
				([name, value]) =>
					!/^[\w.-]{1,160}$/.test(name) ||
					typeof value !== 'string' ||
					!(value.toUpperCase() in levels)
			)
		)
			throw new Error();
	} catch {
		throw new Error('Invalid IRIS_LOG_LEVELS');
	}
	const matched = Object.keys(overrides)
		.filter((name) => 'iris.frontend' === name || 'iris.frontend'.startsWith(name + '.'))
		.sort((a, b) => b.length - a.length)[0];
	const configured = (overrides[matched] || level).toUpperCase();
	if (!(configured in levels) || !['json', 'text'].includes(env.IRIS_LOG_FORMAT || 'json'))
		throw new Error('Invalid logging configuration');
	serverLevel = configured as Level;
	serverFormat = env.IRIS_LOG_FORMAT || 'json';
	serverContext = context;
}

export function getLogRequestId(): string | undefined {
	const value = browser ? undefined : serverContext().request_id;
	return typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value) ? value : undefined;
}

function localLevel(): Level {
	if (!browser) return serverLevel;
	try {
		const value = localStorage.getItem('iris_log_level')?.toUpperCase();
		if (value && value in levels) return value as Level;
		return localStorage.getItem('debug_api') === 'true' ? 'DEBUG' : 'INFO';
	} catch {
		return 'INFO';
	}
}

export const logger = createLogger({
	level: localLevel,
	context: () => (browser ? { request_id: getLastRequestId() ?? undefined } : serverContext()),
	sink: (row) => {
		const method =
			row.level === 'ERROR' || row.level === 'CRITICAL'
				? 'error'
				: row.level === 'WARNING'
					? 'warn'
					: 'log';
		console[method](
			!browser && serverFormat === 'text'
				? Object.entries(row)
						.map(([k, v]) => `${k}=${JSON.stringify(v)}`)
						.join(' ')
				: JSON.stringify(row)
		);
	},
	forward: (event) => {
		if (browser) transport?.enqueue(event);
	}
});

export function startClientLogging(
	getToken: () => string | null | undefined,
	getSession: () => number | null
) {
	if (!browser || transport) return;
	transport = createClientTransport(async (body) => {
		const token = getToken();
		if (!token) return;
		const controller = new AbortController();
		const timeout = setTimeout(() => controller.abort(), 5000);
		try {
			await fetch('/api/v2/observability/client-events', {
				method: 'POST',
				credentials: 'same-origin',
				signal: controller.signal,
				headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
				body: JSON.stringify(body)
			});
		} finally {
			clearTimeout(timeout);
		}
	}, getSession);
	window.addEventListener('error', (event) => logger.error('browser_unhandled_error', event.error));
	window.addEventListener('unhandledrejection', (event) =>
		logger.error('browser_unhandled_rejection', event.reason)
	);
}
