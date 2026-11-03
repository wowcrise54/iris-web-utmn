export const MAX_CHATBOT_LIMIT = 2_147_483_647;
export const CHATBOT_LIMIT_ERROR =
	'Limits must be whole numbers from 0 to 2147483647. Choose Unlimited to remove a limit.';
const limitFields = new Set([
	'max_output_tokens',
	'max_turns_per_conversation',
	'max_tool_calls_per_turn',
	'daily_token_budget_per_user',
	'daily_token_budget_org'
]);
export function validChatbotLimit(value: unknown): value is number {
	return (
		typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= MAX_CHATBOT_LIMIT
	);
}
export function invalidChatbotLimits(body: object): boolean {
	return Object.entries(body).some(
		([key, value]) => limitFields.has(key.replace(/^chatbot_/, '')) && !validChatbotLimit(value)
	);
}
