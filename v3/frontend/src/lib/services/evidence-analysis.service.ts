import { ApiService } from './api.service';

export interface AnalysisSource {
	file_id?: number;
	scan_id?: number;
	log_id?: number;
}
export interface AnalysisFlow extends Record<string, unknown> {
	id: string;
	from: string;
	to: string;
	port: string;
	protocol: string;
	packets: number;
	bytes: number;
	first_frame: number;
	first_seen: number;
	last_seen: number;
	label: string;
}
export interface AnalysisJob {
	id: number;
	case_id: number;
	kind: 'pcap' | 'sandbox';
	status: string;
	progress: number;
	total: number;
	error: string | null;
	conversation_id: number | null;
	source_url: string;
	result: {
		summary?: string;
		partial_response?: string;
		source?: AnalysisSource;
		partial?: boolean;
		sha256?: string;
		packets?: number;
		bytes?: number;
		first_seen?: number;
		last_seen?: number;
		original_sha256?: string;
		nodes?: { id: string; label: string; group: string }[];
		edges?: AnalysisFlow[];
		indicators?: { value: string; frame: number; timestamp: number }[];
		omissions?: string[];
		sources?: { source: string; offset: number; end_offset: number; source_url?: string }[];
	};
}
export class EvidenceAnalysisService {
	static list(caseId: number) {
		return ApiService.get<{ analyses: AnalysisJob[] }>(`/cases/${caseId}/analysis`);
	}
	static get(caseId: number, id: number) {
		return ApiService.get<AnalysisJob>(`/cases/${caseId}/analysis/${id}`);
	}
	static start(
		caseId: number,
		body: AnalysisSource & { kind: 'pcap' | 'sandbox'; conversation_id?: number }
	) {
		return ApiService.post<AnalysisJob>(`/cases/${caseId}/analysis`, body);
	}
	static resume(caseId: number, id: number) {
		return ApiService.post<AnalysisJob>(`/cases/${caseId}/analysis/${id}/continue`, {});
	}
}
