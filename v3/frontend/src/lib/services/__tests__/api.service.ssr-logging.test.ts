import { expect, it, vi } from 'vitest';
import { ApiService } from '../api.service';
import { configureServerLogging } from '$lib/observability/logger';

vi.mock('$app/environment', () => ({ browser: false, dev: false, building: false }));

it('preserves the SSR request ID in its backend fetch', async () => {
	configureServerLogging({ LOG_LEVEL: 'INFO' }, () => ({ request_id: 'incoming-ssr-request' }));
	let identifier: string | null = null;
	await ApiService.get('/cases', {
		skipTokenRefresh: true,
		skipAuthRedirect: true,
		fetch: async (_input, init) => {
			identifier = new Headers(init?.headers).get('X-Request-Id');
			return new Response(JSON.stringify({ data: [] }), { status: 200 });
		}
	});
	expect(identifier).toBe('incoming-ssr-request');
});
