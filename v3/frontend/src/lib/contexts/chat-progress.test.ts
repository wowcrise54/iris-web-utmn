import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatSocketHandlers } from '$lib/services/chat.service';

const mock = vi.hoisted(() => ({
	handlers: {} as ChatSocketHandlers,
	getConversation: vi.fn(),
	createGlobalConversation: vi.fn(),
	startAnalysis: vi.fn(),
	getAnalysis: vi.fn(),
	listAnalysis: vi.fn(),
	retryAnalysis: vi.fn(),
	cancelAnalysis: vi.fn(),
	send: vi.fn()
}));
vi.mock('$lib/services/chat.service', () => ({
	ChatService: {
		getConversation: mock.getConversation,
		createGlobalConversation: mock.createGlobalConversation
	},
	ChatSocketClient: class {
		constructor(handlers: ChatSocketHandlers) {
			mock.handlers = handlers;
		}
		connect() {}
		joinConversation() {}
		leaveConversation() {}
		send = mock.send;
		approveTool() {}
		denyTool() {}
		disconnect() {}
	}
}));
vi.mock('$lib/services/alert-analysis.service', () => ({
	AlertAnalysisService: {
		start: mock.startAnalysis,
		get: mock.getAnalysis,
		list: mock.listAnalysis,
		retry: mock.retryAnalysis,
		cancel: mock.cancelAnalysis
	},
	analysisActive: (job: { status: string } | null) =>
		!!job && ['queued', 'running'].includes(job.status)
}));
vi.mock('$lib/components/ui/toast', () => ({ toast: vi.fn() }));
import { createChatPanelContext } from './chat-panel.context.svelte';

let chat: ReturnType<typeof createChatPanelContext>;
const result = { ok: true, data: { id: 1, messages: [], pending_tool_calls: [] } };
beforeEach(async () => {
	mock.getConversation.mockImplementation(async (id: number) => ({
		...result,
		data: { ...result.data, id }
	}));
	chat = createChatPanelContext();
	await chat.openConversation(1);
	chat.send('hello');
});

const job = {
	id: 7,
	alert_id: 42,
	conversation_id: 41,
	status: 'queued',
	stage: 'queued',
	progress: 0,
	total: 2,
	result: null,
	error: null
};
describe('one-click alert analysis', () => {
	it('restores a durable analysis when its alert-scoped history is reopened', async () => {
		mock.handlers.onAssistantEnd?.({ conversation_id: 1 });
		mock.getConversation.mockResolvedValueOnce({
			ok: true,
			data: { ...result.data, id: 41, alert_id: 42 }
		});
		mock.listAnalysis.mockResolvedValueOnce({ ok: true, data: { analyses: [job] } });
		mock.getAnalysis.mockResolvedValueOnce({ ok: true, data: job });
		await chat.openConversation(41);
		expect(mock.listAnalysis).toHaveBeenCalledWith(42);
		expect(chat.state.alertAnalysis?.id).toBe(7);
	});
	beforeEach(() => {
		mock.handlers.onAssistantEnd?.({ conversation_id: 1 });
		mock.send.mockClear();
		mock.startAnalysis.mockResolvedValue({ ok: true, data: job });
	});

	it('starts a durable job and opens its conversation without a raw chat prompt', async () => {
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(true);
		expect(chat.state.open).toBe(true);
		expect(chat.state.revealRequest).toBe(1);
		expect(chat.state.currentConversation?.id).toBe(41);
		expect(mock.startAnalysis).toHaveBeenCalledWith(42);
		expect(mock.send).not.toHaveBeenCalled();
		expect(chat.state.alertAnalysis?.id).toBe(7);
		expect(chat.state.streamingConversationId).toBeNull();
	});

	it('prevents a second launch while creating the conversation', async () => {
		let finish!: (value: unknown) => void;
		mock.startAnalysis.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		const first = chat.analyzeAlert(42, 'Analyze alert #42.');
		expect(await chat.analyzeAlert(43, 'Analyze alert #43.')).toBe(false);
		finish({ ok: true, data: job });
		expect(await first).toBe(true);
		expect(mock.startAnalysis).toHaveBeenCalledTimes(1);
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('preserves an ongoing conversation instead of replacing it', async () => {
		chat.send('Existing work');
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(chat.state.currentConversation?.id).toBe(1);
		expect(mock.startAnalysis).not.toHaveBeenCalled();
	});

	it('preserves a conversation awaiting tool approval before its pending rows refresh', async () => {
		mock.handlers.onAssistantProgress?.({ conversation_id: 1, stage: 'awaiting_approval' });
		expect(chat.canAnalyzeAlert).toBe(false);
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(mock.startAnalysis).not.toHaveBeenCalled();
	});

	it('does not replace a chat opened while the analysis conversation was being created', async () => {
		let finish!: (value: unknown) => void;
		mock.startAnalysis.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		const analysis = chat.analyzeAlert(42, 'Analyze alert #42.');
		await chat.openConversation(2);
		finish({ ok: true, data: job });
		expect(await analysis).toBe(false);
		expect(chat.state.currentConversation?.id).toBe(2);
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('keeps creation errors visible and does not send into the old conversation', async () => {
		mock.startAnalysis.mockResolvedValueOnce({
			ok: false,
			error: { message: 'Access denied' }
		});
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(chat.state.open).toBe(true);
		expect(chat.state.error).toBe('Access denied');
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('handles a failed creation request and unlocks the launch button', async () => {
		mock.startAnalysis.mockRejectedValueOnce(new Error('network failed'));
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(chat.state.loading).toBe(false);
		expect(chat.state.error).toBeTruthy();
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('polls a job while the panel is closed and refreshes its saved final report', async () => {
		vi.useFakeTimers();
		mock.getAnalysis.mockResolvedValue({
			ok: true,
			data: { ...job, status: 'completed', stage: 'final' }
		});
		await chat.analyzeAlert(42);
		chat.closePanel();
		mock.getConversation.mockClear();
		await vi.advanceTimersByTimeAsync(2000);
		expect(chat.state.alertAnalysis?.status).toBe('completed');
		expect(mock.getConversation).toHaveBeenCalledWith(41);
		expect(mock.send).not.toHaveBeenCalled();
	});
	it('bounds failed polling retries and permits a manual status refresh', async () => {
		vi.useFakeTimers();
		mock.getAnalysis.mockRejectedValue(new Error('network unavailable'));
		await chat.analyzeAlert(42);
		await vi.advanceTimersByTimeAsync(20000);
		expect(mock.getAnalysis).toHaveBeenCalledTimes(3);
		expect(chat.state.analysisError).toBe('network unavailable');
		mock.getAnalysis.mockResolvedValue({ ok: true, data: job });
		await chat.loadAlertAnalysis(42, 7);
		expect(chat.state.analysisError).toBeNull();
	});
	it('drops an in-flight poll after logout disconnect', async () => {
		vi.useFakeTimers();
		let finish!: (value: unknown) => void;
		mock.getAnalysis.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		await chat.analyzeAlert(42);
		await vi.advanceTimersByTimeAsync(2000);
		chat.disconnect();
		finish({ ok: true, data: job });
		await Promise.resolve();
		expect(chat.state.alertAnalysis).toBeNull();
		expect(vi.getTimerCount()).toBe(0);
	});
	it('retries only terminal jobs and uses the cancellation endpoint', async () => {
		mock.cancelAnalysis.mockResolvedValue({ ok: true, data: { ...job, status: 'cancelled' } });
		mock.retryAnalysis.mockResolvedValue({ ok: true, data: job });
		await chat.analyzeAlert(42);
		await chat.retryAlertAnalysis();
		expect(mock.retryAnalysis).not.toHaveBeenCalled();
		await chat.cancelAlertAnalysis();
		expect(mock.cancelAnalysis).toHaveBeenCalledWith(42, 7);
		await chat.retryAlertAnalysis();
		expect(mock.retryAnalysis).toHaveBeenCalledWith(42, 7);
	});
});
afterEach(() => {
	chat.disconnect();
	vi.clearAllMocks();
	vi.useRealTimers();
});
const start = {
	conversation_id: 1,
	tool_use_id: 'a',
	tool_name: 'iris_case_get',
	arguments: {},
	is_write: false,
	pending: false
};

describe('Yuki progress lifecycle', () => {
	it('waits for the model, streams text and completes with legacy events', () => {
		expect(chat.state.progress?.stage).toBe('waiting_model');
		mock.handlers.onAssistantDelta?.({ conversation_id: 1, text: 'Hello' });
		expect(chat.state.progress?.stage).toBe('responding');
		mock.handlers.onAssistantEnd?.({ conversation_id: 1 });
		expect(chat.state.progress?.stage).toBe('completed');
		expect(chat.state.streamingConversationId).toBeNull();
	});
	it('tracks consecutive tools, including tool errors, then model processing', () => {
		for (const tool_use_id of ['a', 'b']) {
			mock.handlers.onAssistantToolStart?.({ ...start, tool_use_id });
			expect(chat.state.progress?.stage).toBe('executing_tool');
			mock.handlers.onAssistantToolResult?.({ ...start, tool_use_id, error: 'tool failed' });
			expect(chat.state.progress?.stage).toBe('processing_result');
			expect(chat.state.streamingAssistant?.toolUses.at(-1)?.finished).toBe(true);
		}
		mock.handlers.onAssistantProgress?.({ conversation_id: 1, stage: 'processing_result' });
		expect(chat.state.progress?.stage).toBe('processing_result');
	});
	it.each(['approveTool', 'denyTool'] as const)(
		'distinguishes confirmation and resumes after %s',
		(action) => {
			mock.handlers.onAssistantToolStart?.({ ...start, pending: true, is_write: true });
			expect(chat.state.progress?.stage).toBe('awaiting_approval');
			expect(chat.state.streamingConversationId).toBeNull();
			chat[action](2);
			expect(chat.state.progress?.stage).toBe('waiting_model');
			mock.handlers.onAssistantProgress?.({ conversation_id: 1, stage: 'awaiting_approval' });
			expect(chat.state.streamingConversationId).toBeNull();
		}
	);
	it('clears on provider error and disconnect', () => {
		mock.handlers.onError?.({ conversation_id: 1, message: 'Provider unavailable' });
		expect(chat.state.progress).toBeNull();
		chat.send('retry');
		mock.handlers.onDisconnect?.();
		expect(chat.state.progress).toBeNull();
		expect(chat.state.streamingConversationId).toBeNull();
	});
	it('ignores old conversation events and clears when opening a chat', async () => {
		await chat.openConversation(2);
		expect(chat.state.progress).toBeNull();
		// Use a different id from the currently hydrated conversation.
		mock.handlers.onAssistantProgress?.({ conversation_id: 999, stage: 'executing_tool' });
		mock.handlers.onAssistantDelta?.({ conversation_id: 999, text: 'stale' });
		mock.handlers.onError?.({ conversation_id: 999, message: 'stale error' });
		expect(chat.state.progress).toBeNull();
		expect(chat.state.error).toBeNull();
	});
	it('does not restore stale progress when an old history request finishes after switching', async () => {
		let finish!: (value: typeof result) => void;
		mock.getConversation.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		const oldRefresh = chat.refresh(1);
		await chat.openConversation(2);
		finish({ ...result, data: { ...result.data, pending_tool_calls: [] } });
		await oldRefresh;
		expect(chat.state.currentConversation?.id).toBe(2);
		expect(chat.state.progress).toBeNull();
	});
});
