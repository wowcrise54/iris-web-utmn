import { render, screen, cleanup, fireEvent } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatPanelContext } from '$lib/contexts/chat-panel.context.svelte';
import AlertAnalysisProgress from './AlertAnalysisProgress.svelte';
vi.mock('svelte', async () => {
	const clientEntry = '../../../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
afterEach(cleanup);
const job = {
	id: 7,
	alert_id: 42,
	conversation_id: 41,
	status: 'partial',
	stage: 'final',
	progress: 2,
	total: 2,
	error: null,
	result: {
		coverage: {
			available_events: 9,
			processed_events: 9,
			missing_events: [10],
			source_complete: false,
			normalization_complete: true
		}
	}
};
function context(status = 'partial') {
	return {
		state: { alertAnalysis: { ...job, status }, loading: false, analysisError: null },
		canAnalyzeAlert: true,
		retryAlertAnalysis: vi.fn(),
		cancelAlertAnalysis: vi.fn(),
		analyzeAlert: vi.fn()
	} as unknown as ChatPanelContext;
}
describe('durable alert analysis progress', () => {
	it('renders completed stages and starts a new snapshot instead of retrying missing source data', async () => {
		const chat = context();
		chat.state.alertAnalysis!.stage = 'completed';
		render(AlertAnalysisProgress, { chat });
		expect(screen.getByText(/Final report/)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Analyze updated alert' }));
		expect(chat.analyzeAlert).toHaveBeenCalledWith(42);
	});
	it('distinguishes complete packet processing from incomplete original source', async () => {
		const chat = context();
		render(AlertAnalysisProgress, { chat });
		expect(screen.getByText('Packets processed: 2 / 2')).toBeTruthy();
		expect(screen.getByText('Events processed: 9 / 9')).toBeTruthy();
		expect(screen.getByText('Source incomplete: investigation coverage is limited')).toBeTruthy();
		expect(screen.getByText('Missing source events: 1')).toBeTruthy();
		expect(screen.queryByText('Source complete')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Retry analysis' }));
		expect(chat.retryAlertAnalysis).toHaveBeenCalledOnce();
	});
	it('offers cooperative cancellation while the worker is active', async () => {
		const chat = context('running');
		render(AlertAnalysisProgress, { chat });
		expect(screen.queryByRole('button', { name: 'Retry analysis' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel after current request' }));
		expect(chat.cancelAlertAnalysis).toHaveBeenCalledOnce();
	});
});
