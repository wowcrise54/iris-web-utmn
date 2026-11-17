import { ApiService } from './api.service';
import { auth } from '$lib/stores/auth.store';
import { AuthService } from './auth.service';
import { apiOrigin } from '$lib/config/api.config';
import type { UpdateAlertIocBody } from './alerts.service';
import type { Ioc } from '$lib/types/resources/ioc';

export interface AlertArtifact {
	id: number;
	alert_id: number;
	kind: string;
	value: string;
	description: string;
	size_bytes: number | null;
	sha256: string | null;
	created_at: string;
	created_by_id: number;
	created_by_name: string | null;
	updated_at: string | null;
	include_in_case: boolean;
}

export type ArtifactBody = Pick<AlertArtifact, 'kind' | 'value' | 'description' | 'include_in_case'>;

export class AlertMaterialsService {
	static list(id: number) { return ApiService.get<AlertArtifact[]>(`/alerts/${id}/artifacts`); }
	static create(id: number, body: ArtifactBody) {
		return ApiService.post<AlertArtifact>(`/alerts/${id}/artifacts`, body);
	}
	static update(id: number, artifactId: number, body: ArtifactBody) {
		return ApiService.put<AlertArtifact>(`/alerts/${id}/artifacts/${artifactId}`, body);
	}
	static remove(id: number, artifactId: number) {
		return ApiService.delete(`/alerts/${id}/artifacts/${artifactId}`);
	}
	static createIoc(id: number, body: UpdateAlertIocBody) {
		return ApiService.post<Ioc>(`/alerts/${id}/iocs`, body);
	}
	static removeIoc(id: number, iocId: number) {
		return ApiService.delete(`/alerts/${id}/iocs/${iocId}`);
	}
	private static async fileRequest(url: string, body?: FormData) {
		if (auth.isTokenExpired() && !auth.isRefreshTokenExpired()) await AuthService.refreshToken();
		const token = auth.getAccessToken();
		return fetch(`${apiOrigin()}/api/v2${url}`, {
			method: body ? 'POST' : 'GET',
			headers: token ? { Authorization: `Bearer ${token}` } : {},
			body
		});
	}
	static async upload(id: number, file: File, description: string, includeInCase: boolean): Promise<void> {
		const body = new FormData();
		body.append('file', file);
		body.append('description', description);
		body.append('include_in_case', String(includeInCase));
		const response = await this.fileRequest(`/alerts/${id}/artifacts`, body);
		if (!response.ok) throw new Error('File upload failed');
	}
	static async download(id: number, row: AlertArtifact): Promise<void> {
		const response = await this.fileRequest(`/alerts/${id}/artifacts/${row.id}/content`);
		if (!response.ok) throw new Error('File download failed');
		const url = URL.createObjectURL(await response.blob());
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = row.value;
		anchor.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
}
