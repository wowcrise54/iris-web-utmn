export type GraphGroup = 'asset' | 'ioc' | 'node';

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
	label?: string;
	event_ids: number[];
};

export type GraphViewState = {
	positions: Record<string, { x: number; y: number }>;
	center: { x: number; y: number };
	scale: number;
	search: string;
	show_assets: boolean;
	show_iocs: boolean;
	show_manual_nodes: boolean;
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
	event_ids?: number[];
	remove?: boolean;
};
