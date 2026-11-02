import { ApiService } from './api.service';

export interface AlertAnalysisJob {
	id: string | number;
	alert_id: number;
	conversation_id: number;
	status: 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';
	stage: 'queued' | 'normalize' | 'map' | 'reduce' | 'verify' | 'final' | 'completed' | 'failed' | 'cancelled';
	progress: number;
	total: number;
	result: {
		summary?: string;
		coverage?: {
			available_events: number;
			processed_events: number;
			missing_events: (string | number)[];
			source_complete: boolean;
			normalization_complete: boolean;
		};
		stats?: Record<string, unknown>;
		usage?: {budget_method: string; last_request_bytes: number};
	} | null;
	error: string | null;
}
export const analysisActive = (job: AlertAnalysisJob | null) =>
	!!job && ['queued', 'running'].includes(job.status);
const path = (alertId: number, jobId?: string | number) =>
	`/alerts/${alertId}/analysis${jobId == null ? '' : `/${encodeURIComponent(jobId)}`}`;
export class AlertAnalysisService {
	static list(alertId: number) {
		return ApiService.get<{ analyses: AlertAnalysisJob[] }>(path(alertId));
	}
	static start(alertId: number) {
		return ApiService.post<AlertAnalysisJob>(path(alertId), {});
	}
	static get(alertId: number, jobId: string | number) {
		return ApiService.get<AlertAnalysisJob>(path(alertId, jobId));
	}
	static retry(alertId: number, jobId: string | number) {
		return ApiService.post<AlertAnalysisJob>(`${path(alertId, jobId)}/retry`, {});
	}
	static cancel(alertId: number, jobId: string | number) {
		return ApiService.post<AlertAnalysisJob>(`${path(alertId, jobId)}/cancel`, {});
	}
}
