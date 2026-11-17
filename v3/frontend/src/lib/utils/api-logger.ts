import { browser } from '$app/environment';
import { logger } from '$lib/observability/logger';

// Preserve the debug panel API; payload switches are ignored by policy.
export const ApiLoggerConfig = {
	enabled: false,
	logRequestBody: false,
	logResponseBody: false,
	truncateBodyAt: 1000,
	colorizeOutput: browser
};

export class ApiLogger {
	static configure(options: Partial<typeof ApiLoggerConfig>) {
		Object.assign(ApiLoggerConfig, options, { logRequestBody: false, logResponseBody: false });
	}
	static enable() {
		if (browser) {
			try {
				localStorage.setItem('debug_api', 'true');
			} catch {
				/* restricted storage */
			}
		}
		ApiLoggerConfig.enabled = true;
	}
	static disable() {
		if (browser) {
			try {
				localStorage.removeItem('debug_api');
			} catch {
				/* restricted storage */
			}
		}
		ApiLoggerConfig.enabled = false;
	}
	static logRequest(method: string, url: string, headers: Record<string, string>, _body?: unknown) {
		logger.debug('http_started', {
			method,
			path: url,
			request_id: headers['x-request-id'] || headers['X-Request-Id']
		});
	}
	static logResponse(
		method: string,
		url: string,
		status: number,
		headers: Record<string, string>,
		_body?: unknown,
		duration?: number
	) {
		const details = {
			method,
			path: url,
			status,
			duration_ms: duration,
			request_id: headers['x-request-id'] || headers['X-Request-Id']
		};
		if (status >= 500) logger.error('http_failed', details);
		else if (status >= 400) logger.warn('http_rejected', details);
		else logger.debug('http_completed', details);
	}
}
