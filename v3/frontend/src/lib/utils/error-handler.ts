import { logger } from '$lib/observability/logger';
/**
 * Utility functions for error handling
 */

/**
 * Safely logs errors without causing additional issues
 */
export function safeLogError(context: string, error: any): void {
	try {
		logger.error('operation_failed', error, { stage: context });
	} catch (_loggingError) {
		// Last resort if even logging fails
		logger.error('Failed to log error details');
	}
}

/**
 * Determines if an error is related to CORS
 */
export function isCorsError(error: any): boolean {
	if (!error) return false;

	const errorMessage = error instanceof Error ? error.message : String(error);
	return errorMessage.includes('CORS') || (error.cause && String(error.cause).includes('CORS'));
}
