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
