import { ApiService } from './api.service';
import { auth } from '$lib/stores/auth.store';
import { AuthService } from './auth.service';

export interface SandboxLog {
	id: number; name: string; kind: string; size: number | null; sha256: string | null; error: string | null;
}
export interface SandboxTaskMatch {
	sid: string; started_at: string; object_name: string; status: string; verdict: string; verdict_is_final: number;
}
export interface SandboxScan {
	id: number; case_id: number; file_id: number | null; war_room_id: number | null; file_name: string;
	sha256: string | null; status: string; scan_id: string | null; verdict: string | null; error: string | null;
	created_at: string; finished_at: string | null; logs?: SandboxLog[];
	remote_task?: { start?: string; started_utc?: string; status: string; priority: number; verdict_is_final: number };
	mcp_started_at?: string;
	behavioral_events?: { total: number; included: number; truncated: boolean };
}
export interface SandboxList { enabled: boolean; checks: SandboxScan[]; target_version: string }

export function isSandboxCapture(log: Pick<SandboxLog, 'name' | 'kind' | 'error'>) {
	return !log.error && /\.(pcap|pcapng)(\.(gz|zst))?$/i.test(log.name);
}

export class SandboxService {
	static list(caseId: number, before?: number) {
		return ApiService.get<SandboxList>(ApiService.withQuery(`/cases/${caseId}/sandbox`, { before }));
	}
	static get(caseId: number, scanId: number) {
		return ApiService.get<SandboxScan>(`/cases/${caseId}/sandbox/${scanId}`);
	}
	static search(caseId: number, name: string, days: number) {
		return ApiService.get<{ tasks: SandboxTaskMatch[] }>(
			ApiService.withQuery(`/cases/${caseId}/sandbox/search`, { name, days })
		);
	}
	static create(caseId: number, scanId: string, startedAt: string) {
		return ApiService.post<SandboxScan>(`/cases/${caseId}/sandbox`, {
			scan_id: scanId, started_at: startedAt, include_events: true
		});
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
