export type GraphSuggestion = {
	source: string;
	target: string;
	relation: string;
	directed: boolean;
	event_ids: number[];
	rationale: string;
};

export function parseGraphSuggestions(
	text: string,
	nodeKeys: ReadonlySet<string>,
	relationNames: ReadonlySet<string>
): GraphSuggestion[] {
	if (text.length > 24_000) return [];
	const json = text.trim().replace(/^(```(?:json)?\s*)([\s\S]*?)\s*```$/i, '$2');
	let value: unknown;
	try {
		value = JSON.parse(json);
	} catch {
		return [];
	}
	if (!Array.isArray(value)) return [];
	const suggestions: GraphSuggestion[] = [];
	for (const row of value.slice(0, 5)) {
		if (!row || typeof row !== 'object') continue;
		const { source, target, relation, directed, event_ids, rationale } = row;
		if (
			typeof source !== 'string' ||
			!nodeKeys.has(source) ||
			typeof target !== 'string' ||
			!nodeKeys.has(target) ||
			source === target ||
			typeof relation !== 'string' ||
			!relationNames.has(relation) ||
			typeof directed !== 'boolean' ||
			!Array.isArray(event_ids) ||
			!event_ids.length ||
			event_ids.length > 20 ||
			event_ids.some(
				(id: unknown) => typeof id !== 'number' || !Number.isSafeInteger(id) || id < 1
			) ||
			typeof rationale !== 'string' ||
			!rationale.trim()
		)
			continue;
		suggestions.push({
			source,
			target,
			relation,
			directed,
			event_ids: [...new Set<number>(event_ids)],
			rationale: rationale.trim().slice(0, 500)
		});
	}
	return suggestions;
}
