import { ApiService, type ApiOptions } from './api.service';

export interface SiemEventPage {
	data: { event_key: string; event: Record<string, unknown>; error?: string; bytes?: number }[];
	offset: number;
	next_offset: number | null;
	has_more: boolean;
	total: number;
	limit: number;
}

export function hasMaxPatrolEvents(source: unknown): boolean {
	if (!source || typeof source !== 'object') return false;
	const storage = (source as Record<string, unknown>).event_storage;
	return (
		!!storage &&
		typeof storage === 'object' &&
		(storage as Record<string, unknown>).kind === 'maxpatrol'
	);
}

export class SiemEventsService {
	static list(alertId: number, offset = 0, options: ApiOptions = {}) {
		return ApiService.get<{ status: string; data: SiemEventPage }>(
			ApiService.withQuery(`/api/v2/alerts/${alertId}/siem-events`, { offset, limit: 25 }),
			options
		);
	}
}
