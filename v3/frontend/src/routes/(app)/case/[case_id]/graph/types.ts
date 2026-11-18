export type GraphGroup = 'asset' | 'ioc' | 'node' | 'event' | 'evidence' | 'task' | 'note';

export const graphRelationLabels: Record<string, string> = {
	related_to: 'Related to',
	connected_to: 'Connected to',
	authenticated_to: 'Authenticated to',
	lateral_movement: 'Lateral movement',
	executed_on: 'Executed on',
	dropped: 'Dropped',
	downloaded_from: 'Downloaded from',
	resolves_to: 'Resolves to',
	beacons_to: 'Beacons to',
	exfiltrated_to: 'Exfiltrated to',
	owns_account: 'Owns account',
	same_as: 'Same as',
	co_occurs: 'Seen together'
} as const;

export type GraphRelation = string;
export type { GraphRelationType } from '$lib/types/resources/case-graph';

export type GraphNode = {
	id?: number;
	key: string;
	kind: GraphGroup;
	label: string;
	description?: string | null;
	subtitle?: string | null;
	icon?: string | null;
};

export type GraphEdge = {
	id?: number;
	key: string;
	source: string;
	target: string;
	directed: boolean;
	origin?: string;
	relation?: GraphRelation | null;
	label?: string;
	event_ids: number[];
};

export type GraphViewState = {
	layout?: string;
	positions: Record<string, { x: number; y: number }>;
	center: { x: number; y: number };
	scale: number;
	search: string;
	show_assets: boolean;
	show_iocs: boolean;
	show_manual_nodes: boolean;
	show_events?: boolean;
	include_objects?: string[];
};

export type GraphView = { id: number; label: string; state: GraphViewState };
export type GraphResource = 'nodes' | 'edges' | 'views';

export type GraphEdit = {
	resource: GraphResource;
	id?: number;
	label?: string;
	description?: string | null;
	source?: string;
	target?: string;
	directed?: boolean;
	relation?: GraphRelation | null;
	event_ids?: number[];
	remove?: boolean;
};
