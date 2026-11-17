import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import LimitInput from './LimitInput.svelte';
import { invalidChatbotLimits, validChatbotLimit } from '$lib/utils/chatbot-limits';
vi.mock('svelte', async () => {
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
afterEach(() => cleanup());
describe('Yuki limits', () => {
	it('stores unlimited as zero and restores the last finite setting', async () => {
		const onChange = vi.fn();
		const view = render(LimitInput, {
			id: 'limit',
			label: 'Token budget',
			value: 1234,
			fallback: 500,
			onChange
		});
		await fireEvent.click(screen.getByRole('switch', { name: 'Token budget: Unlimited' }));
		expect(onChange).toHaveBeenLastCalledWith(0);
		await view.rerender({ value: 0 });
		expect(
			(screen.getByRole('spinbutton', { name: 'Token budget' }) as HTMLInputElement).disabled
		).toBe(true);
		await fireEvent.click(screen.getByRole('switch', { name: 'Token budget: Unlimited' }));
		await waitFor(() => expect(onChange).toHaveBeenLastCalledWith(1234));
	});
	it('shows saved unlimited values and uses a finite default when re-enabled', async () => {
		const onChange = vi.fn();
		render(LimitInput, { id: 'limit', label: 'Answer', value: 0, fallback: 2048, onChange });
		expect(
			screen.getByRole('switch', { name: 'Answer: Unlimited' }).getAttribute('aria-checked')
		).toBe('true');
		await fireEvent.click(screen.getByRole('switch', { name: 'Answer: Unlimited' }));
		expect(onChange).toHaveBeenLastCalledWith(2048);
	});
	it('rejects invalid values before saving global settings or customer policies', () => {
		for (const key of [
			'max_output_tokens',
			'max_turns_per_conversation',
			'max_tool_calls_per_turn',
			'daily_token_budget_per_user',
			'daily_token_budget_org'
		]) {
			for (const prefix of ['', 'chatbot_']) {
				expect(invalidChatbotLimits({ [prefix + key]: 0 })).toBe(false);
				expect(invalidChatbotLimits({ [prefix + key]: 2147483647 })).toBe(false);
				for (const value of [-1, 1.5, 2147483648, Infinity, NaN, null])
					expect(invalidChatbotLimits({ [prefix + key]: value })).toBe(true);
			}
		}
		expect(validChatbotLimit(1000000001)).toBe(true);
	});
});
