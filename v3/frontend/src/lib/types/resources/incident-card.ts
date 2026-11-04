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
	options?: {
		value: string | number;
		label_ru: string;
		label_en: string;
		group_ru?: string;
		group_en?: string;
	}[];
}
export interface IncidentCard {
	schema_version: 1;
	revision: number;
	meta: { case_id: number };
	fields: Record<string, CardField>;
	selections: Record<string, never>;
	derived: {
		importance: 'low' | 'medium' | 'high' | null;
		priority: number | null;
		incident_duration_seconds: number | null;
	};
	catalog: {
		sections: { id: string; label_ru: string; label_en: string; fields: CardDefinition[] }[];
	};
	warnings: string[];
}
export interface CardExport {
	filename: string;
	docx_base64: string;
	html: string;
	revision: number;
	warnings: string[];
}
