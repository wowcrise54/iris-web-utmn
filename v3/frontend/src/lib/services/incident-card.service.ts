import { ApiService, type ApiOptions, type RequestResponse } from './api.service';
import type { IncidentCard, CardExport } from '$lib/types/resources/incident-card';
import { cardPayload } from '$lib/utils/incident-card';
export class IncidentCardError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}
function unwrap<T>(response: RequestResponse<T>): T {
	if (!response.ok || !response.data || typeof response.data !== 'object')
		throw new IncidentCardError(
			response.status,
			response.error?.message ?? `Request failed (${response.status})`
		);
	return response.data as T;
}
export const IncidentCardService = {
	async get(id: number, options: ApiOptions = {}) {
		return unwrap(await ApiService.get<IncidentCard>(`/cases/${id}/incident-card`, options));
	},
	async save(id: number, card: IncidentCard, options: ApiOptions = {}) {
		return unwrap(
			await ApiService.put<IncidentCard>(`/cases/${id}/incident-card`, cardPayload(card), options)
		);
	},
	async export(id: number, zone: string = 'Asia/Yekaterinburg', options: ApiOptions = {}) {
		return unwrap(
			await ApiService.get<CardExport>(
				`/cases/${id}/incident-card/export?timezone=${encodeURIComponent(zone)}`,
				options
			)
		);
	}
};
