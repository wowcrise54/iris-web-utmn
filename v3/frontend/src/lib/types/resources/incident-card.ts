export type CardValue =
	| string
	| number
	| boolean
	| null
	| CardValue[]
	| { [key: string]: CardValue };
export interface CardField {
	value: CardValue;
	mode: 'auto' | 'manual';
	source: string | null;
	status: 'ok' | 'missing' | 'manual';
}
export interface CardDefinition {
	key: string;
	label_ru: string;
	label_en: string;
	type: 'text' | 'textarea' | 'datetime' | 'boolean' | 'choice' | 'multichoice' | 'people';
	auto: boolean;
	options?: { value: string | number; label_ru: string; label_en: string }[];
}
export interface IncidentCard {
	schema_version: 1;
	revision: number;
	meta: {
		case_id: number;
		author: string | null;
		created_at: string | null;
		updated_at: string | null;
		status: string;
	};
	fields: Record<string, CardField>;
	selections: {
		alert_id: number | null;
		affected_asset_ids: number[];
		source_asset_id: number | null;
		target_asset_id: number | null;
		ioc_ids: number[];
		file_ids: number[];
		performed_task_ids: number[];
		planned_task_ids: number[];
	};
	derived: {
		importance: 'low' | 'medium' | 'high' | null;
		priority: number | null;
		incident_duration_seconds: number | null;
		reaction_seconds: number | null;
	};
	catalog: {
		sections: { id: string; label_ru: string; label_en: string; fields: CardDefinition[] }[];
	};
	sources: Record<
		'alerts' | 'assets' | 'iocs' | 'files' | 'tasks',
		{ id: number; label: string }[]
	>;
	warnings: string[];
	completeness: { missing: string[]; total: number; filled: number };
}
export interface CardExport {
	filename: string;
	docx_base64: string;
	html: string;
	revision: number;
	warnings: string[];
}
