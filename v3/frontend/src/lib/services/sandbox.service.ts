import { ApiService } from './api.service';
import { auth } from '$lib/stores/auth.store';
import { AuthService } from './auth.service';

export interface SandboxLog {
	id: number; name: string; kind: string; size: number | null; sha256: string | null; error: string | null;
}
export interface SandboxScan {
	id: number; case_id: number; file_id: number | null; war_room_id: number | null; file_name: string;
	sha256: string; status: string; scan_id: string | null; verdict: string | null; error: string | null;
	created_at: string; finished_at: string | null; logs?: SandboxLog[]; report?: unknown;
	summary?: { scan_state: string | null; threat: string | null; detections: string[] };
}
export interface SandboxList { enabled: boolean; checks: SandboxScan[]; target_version: string }
export interface LogPage { text: string; offset: number; next_offset: number | null; truncated: boolean }

export function isSandboxCapture(log: Pick<SandboxLog, 'name' | 'kind' | 'error'>) {
	return !log.error && /\.(pcap|pcapng)(\.(gz|zst))?$/i.test(log.name);
}

export class SandboxService {
	static fileInfo(caseId: number, fileId: number) {
		return ApiService.get<{ file_name: string; size: number; is_stored_zip: boolean }>(`/cases/${caseId}/sandbox/files/${fileId}/submission-info`);
	}
	static list(caseId: number, before?: number) {
		return ApiService.get<SandboxList>(ApiService.withQuery(`/cases/${caseId}/sandbox`, { before }));
	}
	static get(caseId: number, scanId: number) {
		return ApiService.get<SandboxScan>(`/cases/${caseId}/sandbox/${scanId}`);
	}
	static create(caseId: number, fileId: number, warRoomId?: number) {
		return ApiService.post<SandboxScan>(`/cases/${caseId}/sandbox`, {
			file_id: fileId, war_room_id: warRoomId, confirmed: true
		});
	}
	static resume(caseId: number, scanId: number) {
		return ApiService.post<SandboxScan>(`/cases/${caseId}/sandbox/${scanId}/resume`, {});
	}
	static acknowledge(caseId: number, scanId: number) {
		return ApiService.post<SandboxScan>(`/cases/${caseId}/sandbox/${scanId}/acknowledge`, { confirmed: true });
	}
	static text(caseId: number, scanId: number, logId: number, offset = 0) {
		return ApiService.get<LogPage>(`/cases/${caseId}/sandbox/${scanId}/logs/${logId}?view=text&offset=${offset}`);
	}
	static async download(caseId: number, scanId: number, log: SandboxLog) {
		if (auth.isTokenExpired() && !auth.isRefreshTokenExpired()) await AuthService.refreshToken();
		const token = auth.getAccessToken();
		const res = await fetch(`${(ApiService.baseUrl ?? '').replace(/\/$/, '')}/api/v2/cases/${caseId}/sandbox/${scanId}/logs/${log.id}`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {}, credentials: 'include'
		});
		if (!res.ok) throw new Error('Unable to download log');
		const url = URL.createObjectURL(await res.blob());
		const a = document.createElement('a');
		a.href = url; a.download = log.name.replace(/[\\/]/g, '_'); a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
}
