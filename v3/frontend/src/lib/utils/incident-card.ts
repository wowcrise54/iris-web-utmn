import type { IncidentCard } from '$lib/types/resources/incident-card';
export function toLocalInput(value: string, zone: string): string {
	if (!value) return '';
	const parts = new Intl.DateTimeFormat('en-CA', {
		timeZone: zone,
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hourCycle: 'h23'
	}).formatToParts(new Date(value));
	const p = Object.fromEntries(parts.map((part) => [part.type, part.value]));
	return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
export function fromLocalInput(value: string, zone: string): string {
	if (!value) return '';
	const normalized = value.length === 16 ? `${value}:00` : value;
	const local = Date.parse(`${normalized}Z`);
	if (!Number.isFinite(local)) throw new Error('Invalid date');
	let utc = local;
	for (let i = 0; i < 4; i++) {
		const projected = Date.parse(`${toLocalInput(new Date(utc).toISOString(), zone)}Z`);
		utc += local - projected;
	}
	if (toLocalInput(new Date(utc).toISOString(), zone) !== normalized)
		throw new Error('This time does not exist in the selected timezone');
	return new Date(utc).toISOString();
}
export function cardPayload(card: IncidentCard) {
	return {
		schema_version: card.schema_version,
		revision: card.revision,
		fields: Object.fromEntries(
			Object.entries(card.fields).map(([key, field]) => [
				key,
				{ value: field.value, mode: field.mode }
			])
		),
		selections: card.selections
	};
}

export function deriveCard(fields: IncidentCard['fields']): IncidentCard['derived'] {
	const value = (key: string) => fields[key]?.value;
	const categories = Array.isArray(value('categories')) ? (value('categories') as number[]) : [];
	const types = ['auxiliary', 'key', 'target'];
	const column = types.indexOf(String(value('prioritization_type')));
	const levels = ['low', 'medium', 'high'] as const;
	const matrix = [
		[1, 2, 2],
		[2, 2, 2],
		[1, 2, 2],
		[0, 1, 1],
		[0, 0, 1],
		[0, 1, 1],
		[0, 0, 0],
		[0, 0, 0]
	];
	const ranks =
		column < 0
			? []
			: categories
					.filter((c) => Number.isInteger(c) && c >= 1 && c <= 8)
					.map((c) => matrix[c - 1][column]);
	const rank = ranks.length ? Math.max(...ranks) : null;
	const importance = rank === null ? null : levels[rank];
	const base =
		rank === null
			? null
			: [
					[9, 8, 6],
					[7, 5, 3],
					[4, 2, 1]
				][column][rank];
	const override = fields.priority_override;
	const priority =
		override?.mode === 'manual' && typeof override.value === 'number' ? override.value : base;
	const start = value('occurred_at'),
		end = value('incident_ended_at');
	const seconds =
		typeof start === 'string' && typeof end === 'string'
			? (Date.parse(end) - Date.parse(start)) / 1000
			: NaN;
	return {
		importance,
		priority,
		incident_duration_seconds:
			value('completed') === true && Number.isFinite(seconds) && seconds >= 0
				? Math.floor(seconds)
				: null
	};
}
