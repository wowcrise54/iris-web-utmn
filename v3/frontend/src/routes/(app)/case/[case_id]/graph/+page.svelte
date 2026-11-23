<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { mode } from 'mode-watcher';
	import { getContext, tick } from 'svelte';
	import {
		CASE_ACCESS_CTX,
		type CaseAccessContext
	} from '$lib/contexts/case-access.context.svelte';
	import PathFinder from './PathFinder.svelte';
	import GraphTable from './GraphTable.svelte';
	import GraphEditDialog from './graph-edit-dialog.svelte';
	import { graphRelationLabels } from './types';
	import type { GraphRelationType } from './types';
	import type {
		GraphEdit,
		GraphEdge,
		GraphGroup as Group,
		GraphNode,
		GraphView,
		GraphViewState
	} from './types';
	import type { Core } from 'cytoscape';
	import DOMPurify from 'dompurify';
	import {
		FingerprintIcon,
		CalendarIcon,
		HardDriveIcon,
		MaximizeIcon,
		RefreshCwIcon,
		SearchIcon,
		XIcon,
		ZoomInIcon,
		ZoomOutIcon,
		ChevronRightIcon,
		ExternalLinkIcon
	} from 'lucide-svelte';
	import iocSvg from 'lucide-static/icons/link.svg?raw';
	import assetSvg from 'lucide-static/icons/hard-drive.svg?raw';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { ApiService } from '$lib/services/api.service';
	import { Button } from '$lib/components/ui/button';
	import Input from '$lib/components/ui/input/input.svelte';
	import {
		CytoscapeGraph,
		runLayout,
		paletteHex,
		downloadFile,
		exportPng,
		exportSvg,
		type CyElementDef,
		type CyLayoutName,
		svgToDataUrl,
		withStroke,
		applyAssetImageTheme
	} from '$lib/components/common/CytoscapeGraph';
	import CaseWorkspace from '../components/CaseWorkspace.svelte';

	const access = getContext<CaseAccessContext | undefined>(CASE_ACCESS_CTX);
	const canEdit = $derived(access?.canEdit() ?? false);
	let edit = $state<GraphEdit | null>(null);
	let activeViewId = $state<number | null>(null);

	// Local node model used for the details rail. Mirrors what the
	// AlertClusterCorrelationGraph feeds into its rail so the two graphs
	// stay behaviourally consistent.
	type CaseGraphNode = {
		id: string;
		group: Group;
		label: string;
		title?: string;
		image?: string;
	};

	const caseId = $derived(Number(page.params.case_id));
	const isDark = $derived($mode === 'dark');

	// Per-group palette mirrors the alert-cluster graph so both graphs
	// read as one system. Only assets + iocs here — the case graph has
	// no alert nodes.
	const palette = $derived({
		asset: {
			icon: isDark ? '#34d399' : '#059669',
			border: isDark ? '#34d399' : '#047857',
			label: isDark ? '#6ee7b7' : '#065f46'
		},
		ioc: {
			icon: isDark ? '#60a5fa' : '#2563eb',
			border: isDark ? '#60a5fa' : '#1d4ed8',
			label: isDark ? '#93c5fd' : '#1e40af'
		},
		node: {
			icon: isDark ? '#c4b5fd' : '#7c3aed',
			border: isDark ? '#a78bfa' : '#7c3aed',
			label: isDark ? '#ddd6fe' : '#5b21b6'
		},
		event: {
			icon: isDark ? '#fbbf24' : '#b45309',
			border: isDark ? '#fbbf24' : '#b45309',
			label: isDark ? '#fde68a' : '#92400e'
		}
	});

	const assetFallbackIcon = $derived(svgToDataUrl(withStroke(assetSvg, palette.asset.icon)));
	const iocIcon = $derived(svgToDataUrl(withStroke(iocSvg, palette.ioc.icon)));

	let loading = $state(false);
	let error = $state<string | null>(null);
	type GraphResponse = {
		nodes: GraphNode[];
		edges: GraphEdge[];
		events: { id: number; title: string; date: string | null }[];
		views: GraphView[];
		relation_types: GraphRelationType[];
	};
	const emptyGraph = (): GraphResponse => ({
		nodes: [],
		edges: [],
		events: [],
		views: [],
		relation_types: []
	});
	let graph = $state<GraphResponse>(emptyGraph());
	const activeView = $derived(graph.views.find((item) => item.id === activeViewId));
	let pathOpen = $state(false);
	let tableOpen = $state(false);
	type GraphGap = {
		code: string;
		severity: string;
		node_keys: string[];
		edge_keys: string[];
		message: string;
	};
	let gapsOpen = $state(false);
	let gaps = $state<GraphGap[]>([]);
	let gapsLoading = $state(false);
	let gapsFailed = $state(false);
	let gapsVersion = 0;

	async function toggleGaps() {
		gapsOpen = !gapsOpen;
		const version = ++gapsVersion;
		pathKeys = new Set();
		if (!gapsOpen) return;
		pathOpen = false;
		gaps = [];
		gapsFailed = false;
		gapsLoading = true;
		try {
			const include = [...includedObjects, ...(visibleGroups.event ? ['events'] : [])].join(',');
			const url = ApiService.withQuery(`/cases/${caseId}/graph/gaps`, { include });
			const response = await ApiService.get<GraphGap[]>(url);
			if (version !== gapsVersion) return;
			if (response.ok && Array.isArray(response.data)) gaps = response.data;
			else gapsFailed = true;
		} catch {
			if (version === gapsVersion) gapsFailed = true;
		} finally {
			if (version === gapsVersion) gapsLoading = false;
		}
	}
	let exporting = $state(false);
	let exportFailed = $state(false);
	let importing = $state(false);
	let importFormat = $state('json');
	let importFile = $state<File | null>(null);
	let importFailed = $state(false);
	type ImportResult = { nodes_created: number; edges_created: number; skipped: number };
	let importResult = $state<ImportResult | null>(null);

	async function uploadGraph() {
		if (!importFile || importing) return;
		const identifier = caseId;
		importing = true;
		importFailed = false;
		importResult = null;
		try {
			if (importFile.size > 20 * 1024 * 1024) throw new Error('Graph file too large');
			const content = await importFile.text();
			if (caseId !== identifier) return;
			const response = await ApiService.post<ImportResult>(`/cases/${identifier}/graph/import`, {
				format: importFormat,
				content
			});
			if (caseId !== identifier) return;
			const data = response.data;
			if (!response.ok || !data || typeof data === 'string') throw new Error('Import failed');
			importResult = data;
			await load(identifier, false);
		} catch {
			if (caseId === identifier) importFailed = true;
		} finally {
			importing = false;
		}
	}

	async function downloadGraph(format: string) {
		const identifier = caseId;
		exporting = true;
		exportFailed = false;
		try {
			if (format === 'png' || format === 'svg') {
				if (!network) return;
				const content = format === 'png' ? exportPng(network) : exportSvg(network);
				downloadFile(
					`case-${identifier}-graph.${format}`,
					content,
					format === 'png' ? 'image/png' : 'image/svg+xml'
				);
				return;
			}
			const include = [...includedObjects, ...(visibleGroups.event ? ['events'] : [])].join(',');
			const url = ApiService.withQuery(`/cases/${identifier}/graph/export`, { format, include });
			const response = await ApiService.get<{ filename: string; content: object | string }>(url);
			if (caseId !== identifier) return;
			const data = response.data;
			if (!response.ok || !data || typeof data === 'string') {
				exportFailed = true;
				return;
			}
			const content =
				typeof data.content === 'string' ? data.content : JSON.stringify(data.content, null, 2);
			downloadFile(
				data.filename,
				content,
				format === 'graphml' ? 'application/graphml+xml' : 'application/json'
			);
		} catch {
			if (caseId === identifier) exportFailed = true;
		} finally {
			exporting = false;
		}
	}
	let pathKeys = $state(new Set<string>());
	let selectedEdgeId = $state<string | null>(null);
	const edgeLabel = (edge: GraphEdge, locale: Parameters<typeof irisT>[1]) => {
		if (edge.label) return edge.label;
		if (edge.origin === 'parent_event') return irisT('Parent event', locale);
		return edge.relation
			? irisT(
					graph.relation_types.find((type) => type.name === edge.relation)?.label ??
						graphRelationLabels[edge.relation] ??
						edge.relation,
					locale
				)
			: undefined;
	};
	let loadVersion = 0;
	let network = $state<Core | null>(null);
	let pendingViewState: GraphViewState | null = null;

	// UX state
	let searchQuery = $state('');
	let visibleGroups = $state<
		Record<'asset' | 'ioc' | 'node' | 'event', boolean> & Partial<Record<Group, boolean>>
	>({
		asset: true,
		ioc: true,
		node: true,
		event: false
	});
	const manualEndpoints = $derived(graph.nodes.filter((node) => node.kind !== 'event'));
	let selectedNodeId = $state<string | null>(null);
	let layoutName = $state<CyLayoutName>('fcose');
	let layoutBusy = $state(false);
	const layouts: { value: CyLayoutName; label: string }[] = [
		{ value: 'fcose', label: 'Force layout' },
		{ value: 'dagre', label: 'Hierarchical layout' },
		{ value: 'chronological', label: 'Chronological layout' },
		{ value: 'radial', label: 'Radial layout' },
		{ value: 'grouped', label: 'Grouped layout' },
		{ value: 'grid', label: 'Grid layout' }
	];
	let contextMenu = $state<{ open: boolean; x: number; y: number; node?: CaseGraphNode }>({
		open: false,
		x: 0,
		y: 0
	});
	const graphData = $derived({
		nodes: graph.nodes.map(
			(node): CaseGraphNode => ({
				id: node.key,
				group: node.kind,
				label: node.label,
				title: [node.subtitle, node.description].filter(Boolean).join(' — ') || undefined,
				image: node.icon ?? undefined
			})
		),
		edges: graph.edges.map((edge) => ({ id: edge.key, from: edge.source, to: edge.target }))
	});
	const selectedEdge = $derived(graph.edges.find((edge) => edge.key === selectedEdgeId));
	const selectedEventIds = $derived(new Set(selectedEdge?.event_ids));
	const supportingEvents = $derived(graph.events.filter((event) => selectedEventIds.has(event.id)));

	const groupCounts = $derived.by<Record<Group, number>>(() => {
		const counts: Record<Group, number> = {
			asset: 0,
			ioc: 0,
			node: 0,
			event: 0,
			evidence: 0,
			task: 0,
			note: 0
		};
		for (const n of graphData.nodes) {
			counts[n.group]++;
		}
		return counts;
	});

	const matches = $derived.by<Set<string>>(() => {
		const q = searchQuery.trim().toLowerCase();
		const hits = new Set<string>();
		for (const n of graphData.nodes) {
			if (visibleGroups[n.group] === false) continue;
			const label = (n.label ?? '').toLowerCase();
			const title = (n.title ?? '').toLowerCase();
			if (!q || label.includes(q) || title.includes(q)) hits.add(n.id);
		}
		return hits;
	});

	const searchHitCount = $derived(searchQuery.trim() ? matches.size : 0);
	const hasActiveFilter = $derived(
		searchQuery.trim().length > 0 ||
			!visibleGroups.asset ||
			!visibleGroups.ioc ||
			!visibleGroups.node
	);

	const orderedMatches = $derived.by<string[]>(() => {
		if (!searchQuery.trim()) return [];
		return graphData.nodes.filter((n) => matches.has(n.id)).map((n) => n.id);
	});
	let matchCursor = $state(0);

	const visibleNodeIds = $derived(
		new Set(
			graphData.nodes
				.filter((node) => visibleGroups[node.group] !== false || pathKeys.has(node.id))
				.map((node) => node.id)
		)
	);
	const displayedNodes = $derived(
		graphData.nodes.filter((node) => visibleGroups[node.group] !== false || pathKeys.has(node.id))
	);
	const elements = $derived.by<CyElementDef[]>(() => [
		...displayedNodes.map(
			(node): CyElementDef => ({
				group: 'nodes',
				data: {
					id: node.id,
					label: node.label,
					kind: node.group,
					color: (node.group === 'asset' || node.group === 'ioc' || node.group === 'event'
						? palette[node.group]
						: palette.node
					).border,
					shape: node.group === 'node' || node.group === 'event' ? 'roundrectangle' : 'ellipse',
					image:
						node.group === 'ioc'
							? iocIcon
							: node.group === 'asset'
								? node.image
									? applyAssetImageTheme(node.image, isDark)
									: assetFallbackIcon
								: undefined
				},
				classes: pathKeys.has(node.id)
					? ['highlighted']
					: matches.has(node.id) && !pathKeys.size
						? []
						: ['dimmed']
			})
		),
		...graph.edges
			.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target))
			.map((edge): CyElementDef => {
				const relation = graph.relation_types.find((type) => type.name === edge.relation);
				return {
					group: 'edges',
					data: {
						id: edge.key,
						source: edge.source,
						target: edge.target,
						label: edgeLabel(edge, $irisLocale),
						arrow: edge.directed ? 'triangle' : 'none',
						color: paletteHex(relation?.color, isDark),
						lineStyle: edge.origin === 'manual' ? (relation?.line_style ?? 'solid') : 'dashed',
						width: Math.min(6, 1 + Math.log2(Math.max(1, edge.event_ids.length)))
					},
					classes: pathKeys.has(edge.key)
						? ['highlighted', 'show-label']
						: matches.has(edge.source) && matches.has(edge.target) && !pathKeys.size
							? []
							: ['dimmed']
				};
			})
	]);

	const nodeById = $derived.by(() => {
		const m = new Map<string, CaseGraphNode>();
		for (const n of graphData.nodes) m.set(n.id, n);
		return m;
	});

	const selectedNode = $derived(selectedNodeId ? (nodeById.get(selectedNodeId) ?? null) : null);

	const selectedNeighbours = $derived.by<CaseGraphNode[]>(() => {
		if (!selectedNodeId) return [];
		const neighbourIds = new Set<string>();
		for (const e of graphData.edges) {
			if (e.from === selectedNodeId) neighbourIds.add(e.to as string);
			else if (e.to === selectedNodeId) neighbourIds.add(e.from as string);
		}
		const out: CaseGraphNode[] = [];
		for (const id of neighbourIds) {
			const n = nodeById.get(id);
			if (n) out.push(n);
		}
		return out.sort((a, b) => {
			const order = { asset: 0, ioc: 1, node: 2, event: 3, evidence: 4, task: 5, note: 6 } as const;
			return order[a.group] - order[b.group];
		});
	});

	// Push selection into vis-network without rebuilding the dataset.
	// Rebuilding would drop layout positions and re-trigger stabilization
	// on every click — same bug the alert-cluster graph avoids.
	$effect(() => {
		if (!network) return;
		try {
			if (selectedNodeId) {
				network.elements().unselect();
				network.getElementById(selectedNodeId).select();
			} else if (selectedEdgeId) {
				network.elements().unselect();
				network.getElementById(selectedEdgeId).select();
			} else {
				network.elements().unselect();
			}
		} catch {
			/* vis-network throws if the id isn't in the dataset; ignore */
		}
	});

	const focusNode = (nodeId: string) => {
		selectedEdgeId = null;
		selectedNodeId = nodeId;
		if (network)
			network.animate({ center: { eles: network.getElementById(nodeId) }, duration: 400 });
	};

	const zoomBy = (factor: number) => {
		if (!network) return;
		network.zoom({
			level: network.zoom() * factor,
			renderedPosition: { x: network.width() / 2, y: network.height() / 2 }
		});
	};

	const fit = () => {
		if (network) network.animate({ fit: { eles: network.elements(), padding: 40 }, duration: 400 });
	};

	const applyLayout = async () => {
		if (!network || layoutBusy) return;
		layoutBusy = true;
		const dates = new Map(
			graph.events.map((event) => [event.id, event.date ? Date.parse(event.date) : NaN])
		);
		try {
			await runLayout(network, layoutName, {
				centerId: selectedNodeId ?? undefined,
				groupOf: (id) => nodeById.get(id)?.group ?? '',
				timeOf: (id) => {
					const timestamps = graph.edges
						.filter((edge) => edge.source === id || edge.target === id)
						.flatMap((edge) => edge.event_ids.map((eventId) => dates.get(eventId)))
						.filter((value): value is number => value !== undefined && Number.isFinite(value));
					return timestamps.length ? Math.min(...timestamps) : null;
				}
			});
		} finally {
			layoutBusy = false;
		}
	};

	const handleSearchKeydown = (e: KeyboardEvent) => {
		if (e.key !== 'Enter') return;
		if (orderedMatches.length === 0) return;
		e.preventDefault();
		matchCursor = (matchCursor + 1) % orderedMatches.length;
		focusNode(orderedMatches[matchCursor]);
	};

	$effect(() => {
		void searchQuery;
		matchCursor = 0;
	});

	const handleClick = (detail: { nodeId?: string; edgeId?: string }) => {
		contextMenu = { open: false, x: 0, y: 0 };
		selectedNodeId = typeof detail.nodeId === 'string' ? detail.nodeId : null;
		selectedEdgeId = typeof detail.edgeId === 'string' ? detail.edgeId : null;
	};

	const locateTableRows = async (kind: 'nodes' | 'edges', ids: string[]) => {
		const keys = new Set(ids);
		if (kind === 'edges') {
			for (const edge of graph.edges) {
				if (!keys.has(edge.key)) continue;
				keys.add(edge.source);
				keys.add(edge.target);
			}
		}
		const identifier = caseId;
		pathOpen = false;
		gapsOpen = false;
		gapsVersion++;
		handleClick({});
		pathKeys = keys;
		tableOpen = false;
		await tick();
		if (!network || caseId !== identifier) return;
		const selection = network.elements().filter((element) => keys.has(element.id()));
		if (selection.nonempty()) network.fit(selection, 64);
	};

	const openContextMenu = (detail: { x: number; y: number; nodeId?: string }) => {
		if (typeof detail.nodeId !== 'string') {
			contextMenu = { open: false, x: 0, y: 0 };
			return;
		}
		const node = nodeById.get(detail.nodeId);
		if (!node) {
			contextMenu = { open: false, x: 0, y: 0 };
			return;
		}
		contextMenu = { open: true, x: detail.x, y: detail.y, node };
	};

	const openNode = (node: CaseGraphNode) => {
		if (node.group === 'node' && canEdit) {
			const item = graph.nodes.find((item) => item.key === node.id);
			if (item) edit = { ...item, resource: 'nodes' };
			return;
		}
		if (node.group === 'asset') {
			const numericId = node.id.match(/^asset:(\d+)$/)?.[1];
			if (!numericId) return;
			goto(`/case/${caseId}/assets/${numericId}`);
		} else if (node.group === 'ioc') {
			goto(`/case/${caseId}/iocs/${node.id.slice('ioc:'.length)}`);
		} else if (node.group === 'event') {
			goto(`/case/${caseId}/timeline?event=${node.id.slice('event:'.length)}`);
		} else if (node.group === 'evidence' || node.group === 'task' || node.group === 'note') {
			const route = { evidence: 'evidence', task: 'tasks', note: 'notes' }[node.group];
			goto(`/case/${caseId}/${route}/${node.id.split(':')[1]}`);
		}
	};

	const objectKinds = [
		{ include: 'evidences', label: 'Evidence' },
		{ include: 'tasks', label: 'Tasks' },
		{ include: 'notes', label: 'Notes' }
	];
	let includedObjects = $state<string[]>([]);
	const toggleGroup = (g: Group) => {
		visibleGroups = { ...visibleGroups, [g]: !visibleGroups[g] };
	};

	const applyViewState = (state: GraphViewState) => {
		if (!network) {
			pendingViewState = state;
			return;
		}
		for (const id of visibleNodeIds) {
			const position = state.positions[id];
			if (position) network.getElementById(id).position(position);
		}
		network.viewport({
			zoom: state.scale,
			pan: {
				x: network.width() / 2 - state.center.x * state.scale,
				y: network.height() / 2 - state.center.y * state.scale
			}
		});
		pendingViewState = null;
	};

	const handleReady = (instance: Core | null) => {
		network = instance;
		if (instance && pendingViewState) applyViewState(pendingViewState);
	};

	const load = async (
		identifier: number,
		reset = true,
		includeEvents = !reset && visibleGroups.event,
		objects = reset ? [] : includedObjects
	) => {
		const version = ++loadVersion;
		gapsVersion++;
		gapsOpen = false;
		pathKeys = new Set();
		loading = true;
		error = null;
		if (reset) {
			pendingViewState = null;
			graph = emptyGraph();
			edit = null;
			activeViewId = null;
			searchQuery = '';
			visibleGroups = { asset: true, ioc: true, node: true, event: false };
		}
		contextMenu = { open: false, x: 0, y: 0 };
		selectedNodeId = null;
		selectedEdgeId = null;

		try {
			const includes = [...objects, ...(includeEvents ? ['events'] : [])];
			const query = includes.length ? '?include=' + includes.join(',') : '';
			const response = await ApiService.get<GraphResponse>(
				`/api/v2/cases/${identifier}/graph${query}`,
				{ fetch }
			);
			if (version !== loadVersion) return;
			if (!response.ok || !response.data || typeof response.data === 'string') {
				error = 'Failed to load graph data';
				return;
			}
			graph = response.data;
			visibleGroups.event = includeEvents;
			includedObjects = objects;
			return true;
		} catch {
			if (version === loadVersion) error = 'Failed to load graph data';
		} finally {
			if (version === loadVersion) loading = false;
		}
	};

	$effect(() => {
		void load(caseId);
		return () => {
			loadVersion++;
		};
	});

	const readViewState = (): GraphViewState | null =>
		network
			? {
					layout: layoutName,
					positions: Object.fromEntries(
						network.nodes().map((node) => [node.id(), { ...node.position() }])
					),
					center: {
						x: (network.width() / 2 - network.pan().x) / network.zoom(),
						y: (network.height() / 2 - network.pan().y) / network.zoom()
					},
					scale: network.zoom(),
					search: searchQuery,
					show_assets: visibleGroups.asset,
					show_iocs: visibleGroups.ioc,
					show_manual_nodes: visibleGroups.node,
					show_events: visibleGroups.event,
					include_objects: includedObjects
				}
			: null;

	const restoreView = async (view: GraphView) => {
		if (layoutBusy) return;
		const identifier = caseId;
		const includeEvents = view.state.show_events ?? false;
		const objects = view.state.include_objects ?? [];
		if (
			(visibleGroups.event !== includeEvents || objects.join(',') !== includedObjects.join(',')) &&
			!(await load(identifier, false, includeEvents, objects))
		)
			return;
		if (caseId !== identifier) return;
		activeViewId = view.id;
		layoutName = layouts.find((layout) => layout.value === view.state.layout)?.value ?? 'fcose';
		searchQuery = view.state.search;
		visibleGroups = {
			asset: view.state.show_assets,
			ioc: view.state.show_iocs,
			node: view.state.show_manual_nodes,
			event: includeEvents
		};
		selectedNodeId = null;
		selectedEdgeId = null;
		await tick();
		if (caseId !== identifier || activeViewId !== view.id) return;
		applyViewState(view.state);
	};

	const saveEdit = async (item: GraphEdit, body: Record<string, unknown>) => {
		const identifier = caseId;
		const path = `/api/v2/cases/${identifier}/graph/${item.resource}`;
		if (!item.remove && item.resource === 'views') {
			const state = readViewState();
			if (!state) return false;
			body.state = state;
		}
		try {
			const result = item.remove
				? await ApiService.delete(`${path}/${item.id}`, { fetch })
				: item.id
					? await ApiService.put(`${path}/${item.id}`, body, { fetch })
					: await ApiService.post(path, body, { fetch });
			if (!result.ok) return false;
			if (caseId === identifier) {
				if (item.remove && item.resource === 'views' && activeViewId === item.id)
					activeViewId = null;
				await load(identifier, false);
			}
			return true;
		} catch {
			return false;
		}
	};
</script>

<svelte:head>
	<title>#{page.params.case_id} - {irisT('Graph', $irisLocale)}</title>
</svelte:head>

<CaseWorkspace>
	<div class="flex h-full min-h-0 w-full flex-col">
		<!-- Search, filters, viewport and layouts. -->
		<div class="flex flex-wrap items-center gap-2 border-b bg-muted/20 px-4 py-2">
			<div class="relative min-w-[16rem] max-w-md flex-1">
				<SearchIcon
					class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
				/>
				<Input
					bind:value={searchQuery}
					onkeydown={handleSearchKeydown}
					placeholder={irisT('Search assets, IOCs…  (Enter to cycle)', $irisLocale)}
					class="h-8 pl-8 pr-16 text-xs"
				/>
				{#if searchQuery.trim().length > 0}
					<div class="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-1">
						<span
							class="rounded-sm bg-muted px-1.5 py-0.5 text-2xs tabular-nums text-muted-foreground"
						>
							{searchHitCount}
						</span>
						<button
							type="button"
							class="rounded-sm p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
							aria-label={irisT('Clear search', $irisLocale)}
							onclick={() => (searchQuery = '')}
						>
							<XIcon class="h-3 w-3" />
						</button>
					</div>
				{/if}
			</div>

			<div class="flex items-center gap-1">
				<button
					type="button"
					class="inline-flex h-7 items-center gap-1 rounded-sm border px-2 text-xs transition-colors {visibleGroups.asset
						? irisT(
								'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
								$irisLocale
							)
						: irisT(
								'border-border bg-transparent text-muted-foreground hover:bg-muted/50',
								$irisLocale
							)}"
					onclick={() => toggleGroup('asset')}
					title={irisT('Toggle asset nodes', $irisLocale)}
				>
					<HardDriveIcon class="h-3 w-3" />
					<span>{irisT('Assets', $irisLocale)}</span>
					<span class="tabular-nums">{groupCounts.asset}</span>
				</button>
				<button
					type="button"
					class="inline-flex h-7 items-center gap-1 rounded-sm border px-2 text-xs transition-colors {visibleGroups.ioc
						? irisT(
								'border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300',
								$irisLocale
							)
						: irisT(
								'border-border bg-transparent text-muted-foreground hover:bg-muted/50',
								$irisLocale
							)}"
					onclick={() => toggleGroup('ioc')}
					title={irisT('Toggle IOC nodes', $irisLocale)}
				>
					<FingerprintIcon class="h-3 w-3" />
					<span>{irisT('IOCs', $irisLocale)}</span>
					<span class="tabular-nums">{groupCounts.ioc}</span>
				</button>
			</div>

			<div class="ml-auto flex items-center gap-1">
				<Button
					variant="ghost"
					size="xs"
					onclick={() => zoomBy(1.25)}
					title={irisT('Zoom in', $irisLocale)}
					disabled={!network || loading}
				>
					<ZoomInIcon class="h-3.5 w-3.5" />
				</Button>
				<Button
					variant="ghost"
					size="xs"
					onclick={() => zoomBy(0.8)}
					title={irisT('Zoom out', $irisLocale)}
					disabled={!network || loading}
				>
					<ZoomOutIcon class="h-3.5 w-3.5" />
				</Button>
				<Button
					variant="ghost"
					size="xs"
					onclick={fit}
					title={irisT('Fit to view', $irisLocale)}
					disabled={!network || loading}
				>
					<MaximizeIcon class="h-3.5 w-3.5" />
				</Button>
				<select
					class="h-7 rounded-md border bg-background px-2 text-xs"
					aria-label={irisT('Graph layout', $irisLocale)}
					bind:value={layoutName}
					disabled={!network || loading || layoutBusy}
					onchange={applyLayout}
				>
					{#each layouts as layout (layout.value)}
						<option value={layout.value}>{irisT(layout.label, $irisLocale)}</option>
					{/each}
				</select>
				<Button
					variant="ghost"
					size="xs"
					onclick={() => load(caseId, false)}
					title={irisT('Refresh graph', $irisLocale)}
					disabled={loading}
				>
					<RefreshCwIcon class="h-3.5 w-3.5 {loading ? 'animate-spin' : ''}" />
				</Button>
			</div>
		</div>

		<div class="flex flex-wrap items-center gap-2 border-b px-3 py-2">
			{#if canEdit}
				<Button
					variant="outline"
					size="xs"
					disabled={loading}
					onclick={() => (edit = { resource: 'nodes' })}
				>
					{irisT('Add graph node', $irisLocale)}
				</Button>
				<Button
					variant="outline"
					size="xs"
					disabled={loading || manualEndpoints.length < 2}
					onclick={() =>
						(edit = {
							resource: 'edges',
							source: manualEndpoints.find((node) => node.key === selectedNodeId)?.key
						})}
				>
					{irisT('Add connection', $irisLocale)}
				</Button>
			{/if}
			<Button
				variant={visibleGroups.node ? 'secondary' : 'ghost'}
				size="xs"
				aria-pressed={visibleGroups.node}
				onclick={() => toggleGroup('node')}
			>
				{irisT('Manual nodes', $irisLocale)}
				{groupCounts.node}
			</Button>
			<Button
				variant={visibleGroups.event ? 'secondary' : 'ghost'}
				size="xs"
				disabled={loading}
				aria-pressed={visibleGroups.event}
				onclick={() => load(caseId, false, !visibleGroups.event)}
			>
				{irisT('Events', $irisLocale)}
			</Button>
			{#each objectKinds as kind (kind.include)}
				<Button
					variant={includedObjects.includes(kind.include) ? 'secondary' : 'ghost'}
					size="xs"
					aria-pressed={includedObjects.includes(kind.include)}
					disabled={loading}
					onclick={() =>
						load(
							caseId,
							false,
							visibleGroups.event,
							includedObjects.includes(kind.include)
								? includedObjects.filter((value) => value !== kind.include)
								: [...includedObjects, kind.include]
						)}
				>
					{irisT(kind.label, $irisLocale)}
				</Button>
			{/each}
			<Button
				size="xs"
				variant={pathOpen ? 'secondary' : 'ghost'}
				aria-expanded={pathOpen}
				onclick={() => {
					pathOpen = !pathOpen;
					gapsOpen = false;
					gapsVersion++;
					pathKeys = new Set();
				}}
			>
				{irisT('Find paths', $irisLocale)}
			</Button>
			<Button
				size="xs"
				variant={gapsOpen ? 'secondary' : 'ghost'}
				aria-expanded={gapsOpen}
				disabled={loading}
				onclick={toggleGaps}
			>
				{irisT('Investigation gaps', $irisLocale)}
			</Button>
			<Button
				size="xs"
				variant={tableOpen ? 'secondary' : 'ghost'}
				aria-pressed={tableOpen}
				onclick={() => {
					tableOpen = !tableOpen;
					contextMenu = { open: false, x: 0, y: 0 };
				}}
			>
				{irisT('Graph as tables', $irisLocale)}
			</Button>
			{#if pathKeys.size && !pathOpen && !gapsOpen}
				<Button size="xs" variant="ghost" onclick={() => (pathKeys = new Set())}>
					{irisT('Clear highlight', $irisLocale)}
				</Button>
			{/if}
			<div class="ml-auto flex flex-wrap items-center gap-2">
				<select
					class="rounded-md border bg-background px-2 py-1 text-xs"
					aria-label={irisT('Export graph', $irisLocale)}
					disabled={loading || exporting}
					onchange={(event) => {
						const format = event.currentTarget.value;
						event.currentTarget.value = '';
						if (format) void downloadGraph(format);
					}}
				>
					<option value="">{irisT('Export graph', $irisLocale)}</option>
					<option value="json">JSON</option>
					<option value="stix">STIX 2.1</option>
					<option value="graphml">GraphML</option>
					<option value="png" disabled={!network}>PNG</option>
					<option value="svg" disabled={!network}>SVG</option>
				</select>
				{#if canEdit}
					<details class="text-xs">
						<summary class="cursor-pointer">{irisT('Import graph', $irisLocale)}</summary>
						<form
							class="flex flex-wrap items-center gap-2 py-2"
							onsubmit={(event) => {
								event.preventDefault();
								void uploadGraph();
							}}
						>
							<select
								aria-label={irisT('Import format', $irisLocale)}
								bind:value={importFormat}
								disabled={importing}
							>
								<option value="json">JSON</option>
								<option value="stix">STIX 2.1</option>
							</select>
							<input
								type="file"
								accept=".json,application/json"
								aria-label={irisT('Graph file', $irisLocale)}
								disabled={importing}
								onchange={(event) => {
									importFile = event.currentTarget.files?.[0] ?? null;
								}}
							/>
							<Button type="submit" size="xs" disabled={!importFile || importing || loading}>
								{irisT('Import graph', $irisLocale)}
							</Button>
						</form>
						{#if importFailed}<p role="alert">
								{irisT('Could not import graph', $irisLocale)}
							</p>{/if}
						{#if importResult}
							<p role="status">
								{irisT('Nodes added', $irisLocale)}
								{importResult.nodes_created} ·
								{irisT('Connections added', $irisLocale)}
								{importResult.edges_created} ·
								{irisT('Skipped', $irisLocale)}
								{importResult.skipped}
							</p>
						{/if}
					</details>
				{/if}
				{#if exportFailed}
					<p role="alert" class="text-xs text-destructive">
						{irisT('Could not export graph', $irisLocale)}
					</p>
				{/if}
				<select
					class="max-w-64 rounded-md border bg-background px-2 py-1 text-xs"
					aria-label={irisT('Select a connection', $irisLocale)}
					value={selectedEdgeId ?? ''}
					disabled={loading || graph.edges.length === 0}
					onchange={(event) => {
						selectedNodeId = null;
						selectedEdgeId = event.currentTarget.value || null;
						contextMenu = { open: false, x: 0, y: 0 };
					}}
				>
					<option value="">{irisT('Select a connection', $irisLocale)}</option>
					{#each graph.edges as edge (edge.key)}
						<option value={edge.key}>
							{nodeById.get(edge.source)?.label ?? edge.source}
							{edge.directed ? '→' : '↔'}
							{nodeById.get(edge.target)?.label ?? edge.target}
							{edgeLabel(edge, $irisLocale) ? ' · ' + edgeLabel(edge, $irisLocale) : ''}
						</option>
					{/each}
				</select>
				<select
					class="max-w-56 rounded-md border bg-background px-2 py-1 text-xs"
					aria-label={irisT('Saved graph views', $irisLocale)}
					value={activeViewId ?? ''}
					disabled={loading || layoutBusy}
					onchange={(e) => {
						const view = graph.views.find((item) => item.id === Number(e.currentTarget.value));
						if (view) void restoreView(view);
					}}
				>
					<option value="" disabled>{irisT('Saved graph views', $irisLocale)}</option>
					{#each graph.views as view (view.id)}
						<option value={view.id}>{view.label}</option>
					{/each}
				</select>
				{#if activeView}
					<Button
						variant="ghost"
						size="xs"
						disabled={loading || layoutBusy}
						onclick={() => restoreView(activeView)}
					>
						{irisT('Restore graph view', $irisLocale)}
					</Button>
				{/if}
				{#if canEdit}
					<Button
						variant="outline"
						size="xs"
						disabled={!network || loading || layoutBusy}
						onclick={() => (edit = { resource: 'views' })}
						>{irisT('Save graph view', $irisLocale)}</Button
					>
					{#if activeView}
						<Button
							variant="outline"
							size="xs"
							disabled={!network || loading || layoutBusy}
							onclick={() => (edit = { ...activeView, resource: 'views' })}
						>
							{irisT('Update graph view', $irisLocale)}
						</Button>
						<Button
							variant="ghost"
							size="xs"
							disabled={loading}
							onclick={() => (edit = { ...activeView, resource: 'views', remove: true })}
						>
							{irisT('Delete view', $irisLocale)}
						</Button>
					{/if}
				{/if}
			</div>
		</div>

		{#if gapsOpen}
			<div class="max-h-52 overflow-y-auto border-b px-3 py-2 text-xs" aria-busy={gapsLoading}>
				{#if gapsFailed}
					<p role="alert">{irisT('Could not load investigation gaps', $irisLocale)}</p>
				{:else if !gapsLoading && !gaps.length}
					<p role="status">{irisT('No investigation gaps found', $irisLocale)}</p>
				{:else}
					<ul class="space-y-1">
						{#each gaps as gap}
							<li>
								<button
									type="button"
									class="text-left hover:underline"
									onclick={() => (pathKeys = new Set([...gap.node_keys, ...gap.edge_keys]))}
								>
									{irisT(gap.severity, $irisLocale)} · {gap.message}
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		{/if}
		{#if pathOpen && !loading}
			{#key caseId}
				<PathFinder
					{caseId}
					nodes={graphData.nodes}
					includes={[...includedObjects, ...(visibleGroups.event ? ['events'] : [])]}
					onHighlight={(keys) => (pathKeys = new Set(keys))}
				/>
			{/key}
		{/if}
		<!-- Canvas + right details rail. -->
		<div class="relative flex min-h-0 flex-1">
			<div class="relative flex-1 bg-muted/10">
				{#if tableOpen}
					<GraphTable
						nodes={displayedNodes
							.filter((node) => matches.has(node.id) || pathKeys.has(node.id))
							.map((node) => ({
								id: node.id,
								cells: [node.label, irisT(node.group, $irisLocale)]
							}))}
						edges={graph.edges
							.filter(
								(edge) =>
									visibleNodeIds.has(edge.source) &&
									visibleNodeIds.has(edge.target) &&
									(matches.has(edge.source) || matches.has(edge.target) || pathKeys.has(edge.key))
							)
							.map((edge) => ({
								id: edge.key,
								cells: [
									nodeById.get(edge.source)?.label ?? edge.source,
									edgeLabel(edge, $irisLocale) ?? (edge.directed ? '→' : '↔'),
									nodeById.get(edge.target)?.label ?? edge.target
								]
							}))}
						selectedNode={selectedNodeId}
						selectedEdge={selectedEdgeId}
						onSelect={handleClick}
						onLocate={locateTableRows}
					/>
				{/if}
				{#if graphData.nodes.length > 0 && displayedNodes.length > 0}
					<div class="absolute inset-0" inert={tableOpen}>
						<CytoscapeGraph
							{elements}
							minZoom={0.001}
							maxZoom={20}
							class="h-full w-full"
							selectionType="single"
							onTapNode={(event) => handleClick({ nodeId: event.target.id() })}
							onTapEdge={(event) => handleClick({ edgeId: event.target.id() })}
							onTapCanvas={() => handleClick({})}
							onCxtTapNode={(event) =>
								openContextMenu({
									x: event.renderedPosition.x,
									y: event.renderedPosition.y,
									nodeId: event.target.id()
								})}
							onReady={handleReady}
						/>
					</div>
				{/if}

				{#if contextMenu.open && contextMenu.node}
					<div
						class="absolute z-20 rounded-md border bg-background p-1 shadow-xl"
						style={`left:${contextMenu.x}px;top:${contextMenu.y}px;transform:translate(8px, 8px);`}
					>
						<Button
							variant="ghost"
							size="xs"
							class="w-full justify-start gap-2"
							onclick={() => {
								const node = nodeById.get(contextMenu.node?.id as string);
								if (node) openNode(node);
								contextMenu = { open: false, x: 0, y: 0 };
							}}
						>
							<ExternalLinkIcon class="h-3 w-3" />
							{irisT('View', $irisLocale)}
							{contextMenu.node.group}
							{contextMenu.node.label}
						</Button>
					</div>
				{/if}

				{#if loading}
					<div
						class="absolute inset-0 flex items-center justify-center bg-background/40 text-sm text-muted-foreground backdrop-blur-sm"
					>
						<RefreshCwIcon class="mr-2 h-4 w-4 animate-spin" />
						{irisT('Loading graph…', $irisLocale)}
					</div>
				{:else if error}
					<div class="absolute inset-0 flex items-center justify-center text-sm text-destructive">
						{irisT(error, $irisLocale)}
					</div>
				{:else if !graphData.nodes.length}
					<div
						class="absolute inset-0 flex flex-col items-center justify-center gap-1 text-sm text-muted-foreground"
					>
						<div>{irisT('No graph data.', $irisLocale)}</div>
						<div class="text-xs">
							{irisT(
								'Add assets or IOCs to timeline events and enable "Display in graph".',
								$irisLocale
							)}
						</div>
					</div>
				{:else if displayedNodes.length === 0}
					<div
						class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
					>
						<div>{irisT('Every node is currently filtered out.', $irisLocale)}</div>
						<Button
							variant="outline"
							size="xs"
							onclick={() => {
								visibleGroups = { asset: true, ioc: true, node: true, event: visibleGroups.event };
								searchQuery = '';
							}}
						>
							{irisT('Reset filters', $irisLocale)}
						</Button>
					</div>
				{/if}

				<!-- Legend, bottom-left over the canvas. -->
				<div
					class="pointer-events-none absolute bottom-2 left-2 hidden gap-3 rounded-md border bg-background/80 px-3 py-1.5 text-2xs text-muted-foreground shadow-sm backdrop-blur-sm md:flex"
				>
					<span class="inline-flex items-center gap-1">
						<HardDriveIcon class="h-3 w-3" />
						{irisT('Asset', $irisLocale)}
					</span>
					<span class="inline-flex items-center gap-1">
						<FingerprintIcon class="h-3 w-3" />
						{irisT('IOC', $irisLocale)}
					</span>
				</div>

				{#if graphData.nodes.length > 0 && !hasActiveFilter && !selectedNodeId && !selectedEdgeId}
					<div
						class="pointer-events-none absolute left-2 top-2 max-w-xs rounded-md border bg-background/80 px-2.5 py-1.5 text-2xs text-muted-foreground shadow-sm backdrop-blur-sm"
					>
						{irisT('Select a node or connection to see its details.', $irisLocale)}
					</div>
				{/if}
			</div>

			{#if selectedEdge}
				<aside
					class="flex w-80 shrink-0 flex-col overflow-hidden border-l bg-card"
					aria-label={irisT('Selected connection details', $irisLocale)}
				>
					<header class="flex items-start justify-between gap-2 border-b px-4 py-3">
						<div class="min-w-0 text-sm font-medium">
							{#if edgeLabel(selectedEdge, $irisLocale)}<div>
									{edgeLabel(selectedEdge, $irisLocale)}
								</div>{/if}
							{#if selectedEdge.id && selectedEdge.relation}
								<div class="text-xs text-muted-foreground">
									{irisT(
										graph.relation_types.find((type) => type.name === selectedEdge.relation)
											?.label ??
											graphRelationLabels[selectedEdge.relation] ??
											selectedEdge.relation,
										$irisLocale
									)}
								</div>
							{/if}
							{nodeById.get(selectedEdge.source)?.label}
							{selectedEdge.directed ? '→' : '↔'}
							{nodeById.get(selectedEdge.target)?.label}
						</div>
						<Button
							variant="ghost"
							size="xs"
							onclick={() => (selectedEdgeId = null)}
							title={irisT('Close details', $irisLocale)}
						>
							<XIcon class="h-3.5 w-3.5" />
						</Button>
					</header>
					<div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
						{#if canEdit && selectedEdge.id}
							<div class="mb-3 flex gap-2">
								<Button
									variant="outline"
									size="xs"
									onclick={() => (edit = { ...selectedEdge, resource: 'edges' })}
								>
									{irisT('Edit connection', $irisLocale)}
								</Button>
								<Button
									variant="ghost"
									size="xs"
									onclick={() => (edit = { ...selectedEdge, resource: 'edges', remove: true })}
								>
									{irisT('Delete', $irisLocale)}
								</Button>
							</div>
						{/if}
						<h2 class="mb-2 text-xs font-medium">{irisT('Supporting events', $irisLocale)}</h2>
						{#if !supportingEvents.length}
							<p class="text-xs text-muted-foreground">{irisT('No linked events', $irisLocale)}</p>
						{/if}
						<ul class="space-y-2">
							{#each supportingEvents as event (event.id)}
								<li>
									<a
										class="block rounded border px-2 py-1.5 text-xs hover:bg-muted"
										href={`/case/${caseId}/timeline?event=${event.id}`}
									>
										{event.title}
										{#if event.date}
											<span class="block text-muted-foreground">{event.date.replace('T', ' ')}</span
											>
										{/if}
									</a>
								</li>
							{/each}
						</ul>
					</div>
				</aside>
			{:else if selectedNode}
				<aside
					class="flex w-80 shrink-0 flex-col overflow-hidden border-l bg-card"
					aria-label={irisT('Selected node details', $irisLocale)}
				>
					<header class="flex items-center gap-2 border-b px-4 py-3">
						<div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
							{#if selectedNode.group === 'ioc'}
								<FingerprintIcon class="h-3.5 w-3.5 text-blue-600 dark:text-blue-300" />
							{:else if selectedNode.group === 'event'}
								<CalendarIcon class="h-3.5 w-3.5 text-amber-700 dark:text-amber-300" />
							{:else}
								<HardDriveIcon class="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-300" />
							{/if}
						</div>
						<div class="min-w-0 flex-1">
							<div class="text-2xs uppercase tracking-wide text-muted-foreground">
								{selectedNode.group}
							</div>
							<div class="truncate text-sm font-medium" title={selectedNode.label}>
								{selectedNode.label}
							</div>
						</div>
						<Button
							variant="ghost"
							size="xs"
							onclick={() => (selectedNodeId = null)}
							title={irisT('Close details', $irisLocale)}
						>
							<XIcon class="h-3.5 w-3.5" />
						</Button>
					</header>

					<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
						{#if selectedNode.title}
							<div
								class="rounded-md border bg-muted/20 px-3 py-2 text-xs leading-relaxed [&_b]:font-semibold"
							>
								<!-- eslint-disable-next-line svelte/no-at-html-tags -->
								{@html DOMPurify.sanitize(selectedNode.title, {
									ALLOWED_TAGS: ['b', 'br', 'i', 'em', 'strong', 'span'],
									ALLOWED_ATTR: []
								})}
							</div>
						{/if}

						<div>
							<div
								class="mb-1.5 flex items-center justify-between text-2xs uppercase tracking-wide text-muted-foreground"
							>
								<span>
									{irisT('Connected nodes', $irisLocale)}
								</span>
								<span class="tabular-nums">{selectedNeighbours.length}</span>
							</div>
							<ul class="flex flex-col gap-1">
								{#each selectedNeighbours as n (n.id)}
									<li>
										<button
											type="button"
											class="group flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted/50"
											onclick={() => focusNode(n.id)}
										>
											{#if n.group === 'ioc'}
												<FingerprintIcon class="h-3 w-3 shrink-0 text-blue-500" />
											{:else}
												<HardDriveIcon class="h-3 w-3 shrink-0 text-emerald-500" />
											{/if}
											<span class="min-w-0 flex-1 truncate" title={n.label}>{n.label}</span>
											<ChevronRightIcon
												class="h-3 w-3 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
											/>
										</button>
									</li>
								{:else}
									<li class="px-2 py-1.5 text-xs text-muted-foreground">
										{irisT('No connections.', $irisLocale)}
									</li>
								{/each}
							</ul>
						</div>
					</div>

					<footer class="border-t px-4 py-3">
						{#if selectedNode.group === 'node'}
							{#if canEdit}
								{@const item = graph.nodes.find((node) => node.key === selectedNode.id)}
								{#if item}
									<div class="flex gap-2">
										<Button
											variant="outline"
											size="xs"
											onclick={() => (edit = { ...item, resource: 'nodes' })}
										>
											{irisT('Edit graph node', $irisLocale)}
										</Button>
										<Button
											variant="ghost"
											size="xs"
											onclick={() => (edit = { ...item, resource: 'nodes', remove: true })}
										>
											{irisT('Delete', $irisLocale)}
										</Button>
									</div>
								{/if}
							{/if}
						{:else}
							<Button
								variant="default"
								size="xs"
								class="w-full justify-between"
								onclick={() => openNode(selectedNode)}
							>
								{irisT('Open', $irisLocale)}
								{selectedNode.group}
								<ExternalLinkIcon class="h-3 w-3" />
							</Button>
						{/if}
					</footer>
				</aside>
			{/if}
		</div>
	</div>
</CaseWorkspace>

{#if edit}
	<GraphEditDialog
		{edit}
		nodes={manualEndpoints}
		relationTypes={graph.relation_types}
		onSave={saveEdit}
		onClose={() => (edit = null)}
	/>
{/if}
