import { AsyncLocalStorage } from 'node:async_hooks';
import { env } from '$env/dynamic/private';
import { configureServerLogging, logger } from '$lib/observability/logger';
import type { Handle } from '@sveltejs/kit';

const context = new AsyncLocalStorage<Record<string, unknown>>();
configureServerLogging(env, () => context.getStore() ?? {});
logger.info('service_started');
process.once('exit', () => logger.info('service_stopped'));

export const loggingHandle: Handle = async ({ event, resolve }) => {
	const incoming = event.request.headers.get('X-Request-Id');
	const requestId =
		incoming && /^[A-Za-z0-9_.:-]{1,128}$/.test(incoming) ? incoming : crypto.randomUUID();
	event.request.headers.set('X-Request-Id', requestId);
	const started = performance.now();
	return context.run(
		{ request_id: requestId, method: event.request.method, path: event.url.pathname },
		async () => {
			try {
				const response = await resolve(event);
				response.headers.set('X-Request-Id', response.headers.get('X-Request-Id') || requestId);
				const details = {
					status: response.status,
					duration_ms: Math.round(performance.now() - started)
				};
				if (response.status >= 500) logger.error('http_completed', details);
				else if (response.status >= 400) logger.warn('http_completed', details);
				else logger.debug('http_completed', details);
				return response;
			} catch (error) {
				logger.error('ssr_request_failed', error);
				throw error;
			}
		}
	);
};
