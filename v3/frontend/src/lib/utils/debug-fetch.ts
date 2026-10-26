import { logger } from '$lib/observability/logger';
import { DEV } from 'esm-env';
import type { LoadEvent } from '@sveltejs/kit';

/**
 * A debug wrapper for the fetch function in load functions
 */
export function createDebugFetch(event: LoadEvent) {
	const originalFetch = event.fetch;

	return async (input: RequestInfo | URL, init?: RequestInit) => {
		if (!DEV) {
			return originalFetch(input, init);
		}

		const startTime = Date.now();
		const url = input instanceof Request ? input.url : input.toString();
		const method = init?.method || (input instanceof Request ? input.method : 'GET');

		logger.debug(`[Load] 📤 ${method} ${url}`);

		try {
			const response = await originalFetch(input, init);
			const duration = Date.now() - startTime;

			logger.debug(`[Load] 📥 Response: ${response.status} (${duration}ms)`);

			return response;
		} catch (error) {
			logger.debug('[Load] ❌ Error:', error);

			throw error;
		}
	};
}
