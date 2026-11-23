export type GraphLineStyle = 'solid' | 'dashed' | 'dotted';

export interface GraphRelationType {
	id: number;
	name: string;
	label: string;
	description: string | null;
	directed: boolean;
	color: string;
	line_style: GraphLineStyle;
	stix_relationship: string | null;
	is_system: boolean;
	sort_order: number;
	/** Number of stored edges using the type (catalogue listing only). */
	edge_count?: number;
}

export interface GraphRelationTypeInput {
	name?: string;
	label?: string;
	description?: string | null;
	directed?: boolean;
	color?: string;
	line_style?: GraphLineStyle;
	stix_relationship?: string | null;
	sort_order?: number;
}
export const GRAPH_RELATION_COLORS = [
    'slate', 'gray', 'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald',
    'teal', 'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose'
] as const;
