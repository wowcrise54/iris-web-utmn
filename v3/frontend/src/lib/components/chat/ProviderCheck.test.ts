import { render, fireEvent, screen, waitFor, cleanup } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ProviderCheck from './ProviderCheck.svelte';
import { ChatbotAdminService } from '$lib/services/chatbot-admin.service';
import type { RequestResponse } from '$lib/services/api.service';
import type { ProviderCheckResult } from '$lib/services/chatbot-admin.service';

vi.mock('svelte', async () => {
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});

vi.mock('$lib/services/chatbot-admin.service', () => ({
	ChatbotAdminService: { checkProvider: vi.fn() }
}));
const body = { provider: 'custom', base_url: 'https://example.org/v1', model: 'test-model' };
const result: ProviderCheckResult = {
	models: ['test-model', 'other'],
	models_error: null,
	model: 'test-model',
	model_accessible: true,
	model_error: null
};
const reply = (value = result) =>
	({ ok: true, data: value }) as RequestResponse<ProviderCheckResult>;
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('Provider check', () => {
	it('checks unsaved values and offers returned models', async () => {
		vi.mocked(ChatbotAdminService.checkProvider).mockResolvedValue(reply());
		const onModel = vi.fn();
		render(ProviderCheck, { body: { ...body, api_key: 'unsaved-key' }, onModel });
		await fireEvent.click(screen.getByRole('button', { name: 'Check provider' }));
		await waitFor(() =>
			expect(
				screen.getByText('Selected model responded successfully:', { exact: false })
			).toBeTruthy()
		);
		expect(ChatbotAdminService.checkProvider).toHaveBeenCalledWith({
			...body,
			api_key: 'unsaved-key'
		});
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'other' } });
		expect(onModel).toHaveBeenCalledWith('other');
		expect(screen.queryByText('unsaved-key')).toBeNull();
	});

	it('does not treat model listing as generation access', async () => {
		vi.mocked(ChatbotAdminService.checkProvider).mockResolvedValue(
			reply({ ...result, model_accessible: false, model_error: 'http_403' })
		);
		render(ProviderCheck, { body, onModel: vi.fn() });
		await fireEvent.click(screen.getByRole('button', { name: 'Check provider' }));
		await waitFor(() =>
			expect(screen.getByText('Access denied by provider.', { exact: false })).toBeTruthy()
		);
		expect(
			screen.queryByText('Selected model responded successfully:', { exact: false })
		).toBeNull();
	});

	it('hides stale results when values change during the request', async () => {
		let resolve!: (value: RequestResponse<ProviderCheckResult>) => void;
		vi.mocked(ChatbotAdminService.checkProvider).mockReturnValue(
			new Promise((done) => {
				resolve = done;
			})
		);
		const view = render(ProviderCheck, { body, onModel: vi.fn() });
		await fireEvent.click(screen.getByRole('button', { name: 'Check provider' }));
		expect(screen.getByRole('button')).toBeDisabled();
		await view.rerender({
			body: { ...body, base_url: 'https://other.example/v1' },
			onModel: vi.fn()
		});
		resolve(reply());
		await waitFor(() => expect(screen.getByRole('button')).not.toBeDisabled());
		expect(
			screen.queryByText('Selected model responded successfully:', { exact: false })
		).toBeNull();
	});
});
