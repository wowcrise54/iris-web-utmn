export const openctiStatuses: Record<string, string> = {
	matched: 'Matches found',
	no_match: 'No matches',
	partial: 'Partial results',
	unsupported: 'Unsupported IOC type or value',
	not_checked: 'Not checked',
	unauthorized: 'OpenCTI access denied',
	timeout: 'OpenCTI request timed out',
	unavailable: 'OpenCTI unavailable',
	schema_error: 'OpenCTI schema incompatible',
	configuration_error: 'OpenCTI configuration invalid',
	invalid_response: 'Invalid OpenCTI response',
	result_limit: 'OpenCTI result limit reached',
	busy: 'OpenCTI enrichment busy',
	http_error: 'OpenCTI HTTP error',
	response_too_large: 'OpenCTI response too large',
	pagination_error: 'Invalid OpenCTI pagination',
	active: 'Active',
	revoked: 'Revoked',
	expired: 'Expired',
	not_yet_valid: 'Not yet valid'
};

type Entity = Record<string, unknown> & { id: string };
const record = (value: unknown): Record<string, unknown> | null =>
	value !== null && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;
const entities = (value: unknown): Entity[] =>
	Array.isArray(value)
		? value.filter((v): v is Entity => !!record(v) && typeof v.id === 'string')
		: [];
export const text = (value: unknown): string => (typeof value === 'string' ? value : '');
export const objectText = (value: unknown, key: string): string => text(record(value)?.[key]);
export const markings = (value: unknown): string =>
	Array.isArray(value)
		? value
				.map((v) => objectText(v, 'definition'))
				.filter(Boolean)
				.join(', ')
		: '';

export function safeHttpUrl(value: unknown): string | null {
	try {
		const url = new URL(text(value));
		return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
			? url.href
			: null;
	} catch {
		return null;
	}
}

export function readOpenCTI(enrichment: unknown) {
	const result = record(record(enrichment)?.opencti);
	if (!result || typeof result.status !== 'string') return null;
	return {
		status: result.status,
		checkedAt: text(result.checked_at),
		source: safeHttpUrl(result.source),
		inputValue: objectText(result.input, 'value'),
		inputType: objectText(result.input, 'type'),
		observables: entities(result.observables),
		indicators: entities(result.indicators),
		relationships: entities(result.relationships)
	};
}

export function readOpenCTISummary(attributes: unknown) {
	try {
		const raw = record(record(attributes)?.__iris_opencti)?.value;
		const result = record(typeof raw === 'string' ? JSON.parse(raw) : null);
		if (!result || result.schema_version !== 1 || typeof result.total !== 'number') return null;
		const counts = Object.entries(record(result.counts) ?? {}).filter(
			(entry): entry is [string, number] => typeof entry[1] === 'number'
		);
		const iocs = Array.isArray(result.iocs)
			? result.iocs.map(record).filter((v): v is Record<string, unknown> => v !== null)
			: [];
		return { total: result.total, updatedAt: text(result.updated_at), counts, iocs };
	} catch {
		return null;
	}
}
