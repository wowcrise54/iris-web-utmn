import { logger } from '$lib/observability/logger';
/**
 * Utility functions to debug authentication issues
 */
export function debugAuthRequest() {
	try {
		logger.debug('Authentication Debug Information');

		// Log origin and CORS info
		logger.debug('Page Origin:', window.location.origin);
		logger.debug('API URL:', new URL('/login', window.location.origin).toString());

		// Check for security headers
		fetch('/login', {
			method: 'OPTIONS',
			credentials: 'include'
		})
			.then((response) => {
				logger.debug('OPTIONS response status:', response.status);
			})
			.catch((error) => {
				logger.error('OPTIONS request failed:', error);
			});

	} catch (error) {
		logger.error('Error in auth debugging:', error);
	}
}
