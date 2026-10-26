import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatSocketHandlers } from '$lib/services/chat.service';

const mock = vi.hoisted(() => ({
	handlers: {} as ChatSocketHandlers,
	getConversation: vi.fn(),
	createGlobalConversation: vi.fn(),
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

describe('one-click alert analysis', () => {
	beforeEach(() => {
		mock.handlers.onAssistantEnd?.({ conversation_id: 1 });
		mock.send.mockClear();
		mock.createGlobalConversation.mockResolvedValue({ ok: true, data: { id: 41 } });
	});

	it('opens a fresh conversation and immediately sends the prompt with the selected alert focus', async () => {
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(true);
		expect(chat.state.open).toBe(true);
		expect(chat.state.revealRequest).toBe(1);
		expect(chat.state.currentConversation?.id).toBe(41);
		expect(mock.send).toHaveBeenCalledExactlyOnceWith(
			41,
			'[context: focused on alert #42]\n\nAnalyze alert #42.'
		);
		expect(chat.state.focusHint).toBeNull();
		expect(chat.state.streamingConversationId).toBe(41);
	});

	it('prevents a second launch while creating the conversation', async () => {
		let finish!: (value: unknown) => void;
		mock.createGlobalConversation.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		const first = chat.analyzeAlert(42, 'Analyze alert #42.');
		expect(await chat.analyzeAlert(43, 'Analyze alert #43.')).toBe(false);
		finish({ ok: true, data: { id: 41 } });
		expect(await first).toBe(true);
		expect(mock.createGlobalConversation).toHaveBeenCalledTimes(1);
		expect(mock.send).toHaveBeenCalledTimes(1);
	});

	it('preserves an ongoing conversation instead of replacing it', async () => {
		chat.send('Existing work');
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(chat.state.currentConversation?.id).toBe(1);
		expect(mock.createGlobalConversation).not.toHaveBeenCalled();
	});

	it('preserves a conversation awaiting tool approval before its pending rows refresh', async () => {
		mock.handlers.onAssistantProgress?.({ conversation_id: 1, stage: 'awaiting_approval' });
		expect(chat.canAnalyzeAlert).toBe(false);
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(mock.createGlobalConversation).not.toHaveBeenCalled();
	});

	it('does not replace a chat opened while the analysis conversation was being created', async () => {
		let finish!: (value: unknown) => void;
		mock.createGlobalConversation.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		const analysis = chat.analyzeAlert(42, 'Analyze alert #42.');
		await chat.openConversation(2);
		finish({ ok: true, data: { id: 41 } });
		expect(await analysis).toBe(false);
		expect(chat.state.currentConversation?.id).toBe(2);
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('keeps creation errors visible and does not send into the old conversation', async () => {
		mock.createGlobalConversation.mockResolvedValueOnce({
			ok: false,
			error: { message: 'Access denied' }
		});
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(chat.state.open).toBe(true);
		expect(chat.state.error).toBe('Access denied');
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('handles a failed creation request and unlocks the launch button', async () => {
		mock.createGlobalConversation.mockRejectedValueOnce(new Error('network failed'));
		expect(await chat.analyzeAlert(42, 'Analyze alert #42.')).toBe(false);
		expect(chat.state.loading).toBe(false);
		expect(chat.state.error).toBeTruthy();
		expect(mock.send).not.toHaveBeenCalled();
	});

	it('shows socket connection failure and clears the running state', async () => {
		await chat.analyzeAlert(42, 'Analyze alert #42.');
		mock.handlers.onConnectFailure?.();
		expect(chat.state.open).toBe(true);
		expect(chat.state.error).toContain('Could not connect');
		expect(chat.state.streamingConversationId).toBeNull();
	});
});
afterEach(() => {
	chat.disconnect();
	vi.clearAllMocks();
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
