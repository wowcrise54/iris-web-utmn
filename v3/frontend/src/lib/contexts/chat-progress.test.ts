import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatSocketHandlers } from '$lib/services/chat.service';

const mock = vi.hoisted(() => ({ handlers: {} as ChatSocketHandlers, getConversation: vi.fn() }));
vi.mock('$lib/services/chat.service', () => ({
	ChatService: { getConversation: mock.getConversation },
	ChatSocketClient: class {
		constructor(handlers: ChatSocketHandlers) {
			mock.handlers = handlers;
		}
		connect() {}
		joinConversation() {}
		leaveConversation() {}
		send() {}
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
