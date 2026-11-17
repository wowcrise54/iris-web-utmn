import { logger } from '$lib/observability/logger';
// place files you want to import through the `$lib` alias in this folder.
process.on('unhandledRejection', (reason, promise) => {
	logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
	// Application specific logging, throwing an error, or other logic here
});
