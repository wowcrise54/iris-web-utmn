type ReplayEdge = { key: string; event_ids: number[] };
type ReplayEvent = { id: number; date: string | null };

export function replaySteps(edges: ReplayEdge[], events: ReplayEvent[]) {
	const dates = new Map(events.map(({ id, date }) => [id, Date.parse(date ?? '')]));
	const steps = new Map<number, string[]>();
	for (const edge of edges) {
		let first = Infinity;
		for (const id of edge.event_ids) {
			const date = dates.get(id);
			if (date !== undefined && Number.isFinite(date)) first = Math.min(first, date);
		}
		if (!Number.isFinite(first)) continue;
		const keys = steps.get(first) ?? [];
		keys.push(edge.key);
		steps.set(first, keys);
	}
	return Array.from(steps, ([at, keys]) => ({ at, keys })).sort((a, b) => a.at - b.at);
}
