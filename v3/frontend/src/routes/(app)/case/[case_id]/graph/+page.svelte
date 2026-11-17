<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { mode } from 'mode-watcher';
	import { getContext, tick } from 'svelte';
	import { CASE_ACCESS_CTX, type CaseAccessContext } from '$lib/contexts/case-access.context.svelte';
	import GraphEditDialog from './graph-edit-dialog.svelte';
	import type { GraphEdit, GraphEdge, GraphGroup as Group, GraphNode, GraphView, GraphViewState } from './types';
	import type { IdType, Network, Options } from 'vis-network';
	import DOMPurify from 'dompurify';
	import {
		FingerprintIcon,
		HardDriveIcon,
		MaximizeIcon,
		PauseIcon,
		PlayIcon,
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
	import VisNetwork, {
		type VisNode,
		type VisEdge,
		svgToDataUrl,
		withStroke,
		applyAssetImageTheme
	} from '$lib/components/common/VisNetwork';
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
	const strokeColor = $derived(isDark ? '#f9fafb' : '#111827');

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
	};
	const emptyGraph = (): GraphResponse => ({ nodes: [], edges: [], events: [], views: [] });
	let graph = $state<GraphResponse>(emptyGraph());
	const activeView = $derived(graph.views.find((item) => item.id === activeViewId));
	let selectedEdgeId = $state<string | null>(null);
	let loadVersion = 0;
	let network = $state<Network | null>(null);

	// UX state
	let searchQuery = $state('');
	let visibleGroups = $state<Record<Group, boolean>>({ asset: true, ioc: true, node: true });
	let selectedNodeId = $state<string | null>(null);
	let physicsEnabled = $state(true);
	// Set to true whenever we WANT the next stabilization pass to end
	// with physics turned off. Cleared by the toggle button so a user
	// who explicitly hits Play doesn't get frozen again a beat later.
	let autoFreezeArmed = $state(true);
	let contextMenu = $state<{ open: boolean; x: number; y: number; node?: VisNode }>({
		open: false,
		x: 0,
		y: 0
	});

	const options = $derived({
		autoResize: true,
		layout: { improvedLayout: true, randomSeed: caseId },
		nodes: {
			font: {
				color: strokeColor,
				size: 12,
				strokeWidth: 3,
				strokeColor: isDark ? 'rgba(15,23,42,0.85)' : 'rgba(255,255,255,0.9)'
			},
			borderWidth: 2,
			shadow: false,
			size: 22,
			shapeProperties: { interpolation: false },
			margin: { top: 8, right: 8, bottom: 8, left: 8 },
			scaling: {
				label: { enabled: true, min: 10, max: 18, drawThreshold: 6 }
			}
		},
		edges: {
			smooth: { enabled: true, type: 'dynamic', roundness: 0.5 },
			color: {
				color: isDark ? 'rgba(148,163,184,0.45)' : 'rgba(100,116,139,0.5)',
				highlight: isDark ? '#60a5fa' : '#2563eb',
				opacity: 0.9
			},
			width: 1,
			selectionWidth: 2
		},
		clickToUse: false,
		interaction: { zoomView: true, hover: true, tooltipDelay: 120 },
		// Same barnesHut tuning as the alert-cluster graph — predictable
		// long-range repulsion + `avoidOverlap` so assets/IOCs don't stack
		// on top of one another. Physics runs the initial layout then the
		// `stabilizationIterationsDone` handler in handleReady freezes it.
		physics: {
			enabled: physicsEnabled,
			solver: 'barnesHut',
			barnesHut: {
				gravitationalConstant: -12000,
				centralGravity: 0.15,
				springLength: 180,
				springConstant: 0.04,
				damping: 0.95,
				avoidOverlap: 0.6
			},
			maxVelocity: 30,
			minVelocity: 0.75,
			timestep: 0.35,
			stabilization: {
				enabled: true,
				iterations: 400,
				updateInterval: 50,
				fit: true
			}
		}
	} satisfies Options);

	const graphData = $derived.by(() => {
		const byPair = new Map<string, GraphEdge[]>();
		for (const edge of graph.edges) {
			const pair = JSON.stringify([edge.source, edge.target].sort());
			const parallel = byPair.get(pair) ?? [];
			parallel.push(edge);
			byPair.set(pair, parallel);
		}
		const edges: VisEdge[] = [];
		for (const parallel of byPair.values()) {
			parallel.sort((a, b) => a.key.localeCompare(b.key));
			for (const [index, edge] of parallel.entries()) {
				// Curvature is relative to source → target. Reverse its sign for
				// the opposite orientation so both arrows remain selectable.
				const lane = (index - (parallel.length - 1) / 2) * (edge.source < edge.target ? 1 : -1);
				edges.push({
					id: edge.key,
					from: edge.source,
					to: edge.target,
					arrows: edge.directed ? 'to' : '',
					dashes: !edge.directed,
					label: edge.label,
					smooth: {
						enabled: lane !== 0,
						type: lane > 0 ? 'curvedCW' : 'curvedCCW',
						roundness: Math.abs(lane) / parallel.length
					}
				});
			}
		}
		return {
			nodes: graph.nodes.map((node): CaseGraphNode => ({
				id: node.key,
				group: node.kind,
				label: node.label,
				title: [node.subtitle, node.description].filter(Boolean).join(' — ') || undefined,
				image: node.icon ?? undefined
			})),
			edges
		};
	});
	const selectedEdge = $derived(graph.edges.find((edge) => edge.key === selectedEdgeId));
	const selectedEventIds = $derived(new Set(selectedEdge?.event_ids));
	const supportingEvents = $derived(graph.events.filter((event) => selectedEventIds.has(event.id)));

	const groupCounts = $derived.by<Record<Group, number>>(() => {
		const counts: Record<Group, number> = { asset: 0, ioc: 0, node: 0 };
		for (const n of graphData.nodes) {
			counts[n.group]++;
		}
		return counts;
	});

	const matches = $derived.by<Set<string>>(() => {
		const q = searchQuery.trim().toLowerCase();
		const hits = new Set<string>();
		for (const n of graphData.nodes) {
			if (!visibleGroups[n.group]) continue;
			const label = (n.label ?? '').toLowerCase();
			const title = (n.title ?? '').toLowerCase();
			if (!q || label.includes(q) || title.includes(q)) hits.add(n.id);
		}
		return hits;
	});

	const searchHitCount = $derived(searchQuery.trim() ? matches.size : 0);
	const hasActiveFilter = $derived(
		searchQuery.trim().length > 0 || !visibleGroups.asset || !visibleGroups.ioc || !visibleGroups.node
	);

	const orderedMatches = $derived.by<string[]>(() => {
		if (!searchQuery.trim()) return [];
		return graphData.nodes.filter((n) => matches.has(n.id)).map((n) => n.id);
	});
	let matchCursor = $state(0);

	const dimStroke = $derived(isDark ? '#334155' : '#cbd5e1');
	const dimFont = $derived(isDark ? '#475569' : '#94a3b8');
	const selectedRing = $derived(isDark ? '#60a5fa' : '#2563eb');

	const shortLabel = (label: string | undefined) => {
		const v = label ?? '';
		return v.length > 42 ? `${v.slice(0, 40)}…` : v;
	};

	const nodes = $derived(
		graphData.nodes.map((node) => {
			const isMatch = matches.has(node.id);
			const groupPalette = palette[node.group];

			const borderColor = isMatch ? groupPalette.border : dimStroke;
			const fontColor = isMatch ? groupPalette.label : dimFont;

			const base: VisNode = {
				id: node.id,
				group: node.group,
				label: shortLabel(node.label),
				borderWidth: 2,
				borderWidthSelected: 4,
				color: {
					border: borderColor,
					background: isDark ? '#0f172a' : '#ffffff',
					highlight: {
						border: selectedRing,
						background: isDark ? '#0f172a' : '#ffffff'
					},
					hover: {
						border: groupPalette.border,
						background: isDark ? '#111827' : '#f8fafc'
					}
				} as unknown as VisNode['color'],
				font: {
					color: fontColor,
					size: 12,
					strokeWidth: 3,
					strokeColor: isDark ? 'rgba(15,23,42,0.85)' : 'rgba(255,255,255,0.9)'
				}
			};

			if (node.group === 'ioc') {
				return {
					...base,
					shape: 'circularImage',
					image: iocIcon,
					size: 20
				} as VisNode;
			}
			if (node.group === 'asset' && typeof node.image === 'string') {
				return {
					...base,
					shape: 'circularImage',
					image: applyAssetImageTheme(node.image, isDark),
					brokenImage: assetFallbackIcon,
					size: 22
				} as VisNode;
			}
			// Asset without a resolved icon (name-only, pulled from event).
			return { ...base, shape: 'box' } as VisNode;
		})
	);

	const visibleNodeIds = $derived(
		new Set(graphData.nodes.filter((n) => visibleGroups[n.group]).map((n) => n.id))
	);

	const edges = $derived(
		graphData.edges
			.filter((e) => visibleNodeIds.has(e.from as string) && visibleNodeIds.has(e.to as string))
			.map((e) => {
				const bothHit = matches.has(e.from as string) && matches.has(e.to as string);
				return {
					...e,
					color: bothHit
						? options.edges.color
						: {
								color: isDark ? 'rgba(51,65,85,0.4)' : 'rgba(203,213,225,0.6)',
								opacity: 0.5
							}
				} as VisEdge;
			})
	);

	const displayedNodes = $derived(
		nodes.filter((n) => visibleGroups[(n.group as Group) ?? 'asset'])
	);

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
			const order = { asset: 0, ioc: 1, node: 2 } as const;
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
				network.selectNodes([selectedNodeId]);
			} else if (selectedEdgeId) {
				network.selectEdges([selectedEdgeId]);
			} else {
				network.unselectAll();
			}
		} catch {
			/* vis-network throws if the id isn't in the dataset; ignore */
		}
	});

	const focusNode = (nodeId: string) => {
		selectedEdgeId = null;
		selectedNodeId = nodeId;
		if (!network) return;
		try {
			network.focus(nodeId, {
				scale: 1.2,
				animation: { duration: 400, easingFunction: 'easeInOutQuad' }
			});
		} catch {
			/* ignore */
		}
	};

	const zoomBy = (factor: number) => {
		if (!network) return;
		const scale = network.getScale() * factor;
		network.moveTo({
			scale,
			animation: { duration: 200, easingFunction: 'easeInOutQuad' }
		});
	};

	const fit = () => {
		if (!network) return;
		network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
	};

	const togglePhysics = () => {
		physicsEnabled = !physicsEnabled;
		autoFreezeArmed = false;
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

	const handleClick = (detail: { nodeId?: IdType; edgeId?: IdType }) => {
		contextMenu = { open: false, x: 0, y: 0 };
		selectedNodeId = typeof detail.nodeId === 'string' ? detail.nodeId : null;
		selectedEdgeId = typeof detail.edgeId === 'string' ? detail.edgeId : null;
	};

	const openContextMenu = (detail: { x: number; y: number; nodeId?: IdType }) => {
		if (typeof detail.nodeId !== 'string') {
			contextMenu = { open: false, x: 0, y: 0 };
			return;
		}
		const node = nodeById.get(detail.nodeId);
		if (!node) {
			contextMenu = { open: false, x: 0, y: 0 };
			return;
		}
		contextMenu = { open: true, x: detail.x, y: detail.y, node: node as unknown as VisNode };
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
		}
	};

	const toggleGroup = (g: Group) => {
		visibleGroups = { ...visibleGroups, [g]: !visibleGroups[g] };
	};

	const handleReady = (n: Network | null) => {
		network = n;
		if (!n) return;
		n.on('stabilizationIterationsDone', () => {
			if (!autoFreezeArmed) return;
			physicsEnabled = false;
		});
	};

	const load = async (identifier: number, reset = true) => {
		const version = ++loadVersion;
		loading = true;
		error = null;
		if (reset) {
			graph = emptyGraph();
			edit = null;
			activeViewId = null;
			searchQuery = '';
			visibleGroups = { asset: true, ioc: true, node: true };
		}
		contextMenu = { open: false, x: 0, y: 0 };
		selectedNodeId = null;
		selectedEdgeId = null;
		if (reset) {
			physicsEnabled = true;
			autoFreezeArmed = true;
		}

		try {
			const response = await ApiService.get<GraphResponse>(`/api/v2/cases/${identifier}/graph`, { fetch });
			if (version !== loadVersion) return;
			if (!response.ok || !response.data || typeof response.data === 'string') {
				error = 'Failed to load graph data';
				return;
			}
			graph = response.data;
		} catch {
			if (version === loadVersion) error = 'Failed to load graph data';
		} finally {
			if (version === loadVersion) loading = false;
		}
	};

	$effect(() => {
		void load(caseId);
		return () => { loadVersion++; };
	});

	const readViewState = (): GraphViewState | null => network ? {
		positions: network.getPositions(),
		center: network.getViewPosition(),
		scale: network.getScale(),
		search: searchQuery,
		show_assets: visibleGroups.asset,
		show_iocs: visibleGroups.ioc,
		show_manual_nodes: visibleGroups.node
	} : null;

	const restoreView = async (view: GraphView) => {
		const identifier = caseId;
		activeViewId = view.id;
		autoFreezeArmed = false;
		physicsEnabled = false;
		searchQuery = view.state.search;
		visibleGroups = {
			asset: view.state.show_assets, ioc: view.state.show_iocs, node: view.state.show_manual_nodes
		};
		selectedNodeId = null;
		selectedEdgeId = null;
		await tick();
		if (caseId !== identifier || activeViewId !== view.id || !network) return;
		for (const id of visibleNodeIds) {
			const position = view.state.positions[id];
			if (position) network.moveNode(id, position.x, position.y);
		}
		network.moveTo({ position: view.state.center, scale: view.state.scale });
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
				if (item.remove && item.resource === 'views' && activeViewId === item.id) activeViewId = null;
				await load(identifier, false);
			}
			return true;
		} catch {
			return false;
		}
	};
</script>

<svelte:head>
	<title>#{page.params.case_id} - {irisT("Graph", $irisLocale)}</title>
</svelte:head>

<CaseWorkspace>
	<div class="flex h-full min-h-0 w-full flex-col">
		<!-- Toolbar: search + filter chips + zoom + fit + physics + refresh. -->
		<div class="flex flex-wrap items-center gap-2 border-b bg-muted/20 px-4 py-2">
			<div class="relative min-w-[16rem] max-w-md flex-1">
				<SearchIcon
					class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
				/>
				<Input
					bind:value={searchQuery}
					onkeydown={handleSearchKeydown}
					placeholder={irisT("Search assets, IOCs…  (Enter to cycle)", $irisLocale)}
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
							aria-label={irisT("Clear search", $irisLocale)}
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
						? irisT("border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300", $irisLocale)
						: irisT("border-border bg-transparent text-muted-foreground hover:bg-muted/50", $irisLocale)}"
					onclick={() => toggleGroup('asset')}
					title={irisT("Toggle asset nodes", $irisLocale)}
				>
					<HardDriveIcon class="h-3 w-3" />
					<span>{irisT("Assets", $irisLocale)}</span>
					<span class="tabular-nums">{groupCounts.asset}</span>
				</button>
				<button
					type="button"
					class="inline-flex h-7 items-center gap-1 rounded-sm border px-2 text-xs transition-colors {visibleGroups.ioc
						? irisT("border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300", $irisLocale)
						: irisT("border-border bg-transparent text-muted-foreground hover:bg-muted/50", $irisLocale)}"
					onclick={() => toggleGroup('ioc')}
					title={irisT("Toggle IOC nodes", $irisLocale)}
				>
					<FingerprintIcon class="h-3 w-3" />
					<span>{irisT("IOCs", $irisLocale)}</span>
					<span class="tabular-nums">{groupCounts.ioc}</span>
				</button>
			</div>

			<div class="ml-auto flex items-center gap-1">
				<Button
					variant="ghost"
					size="xs"
					onclick={() => zoomBy(1.25)}
					title={irisT("Zoom in", $irisLocale)}
					disabled={!network || loading}
				>
					<ZoomInIcon class="h-3.5 w-3.5" />
				</Button>
				<Button
					variant="ghost"
					size="xs"
					onclick={() => zoomBy(0.8)}
					title={irisT("Zoom out", $irisLocale)}
					disabled={!network || loading}
				>
					<ZoomOutIcon class="h-3.5 w-3.5" />
				</Button>
				<Button
					variant="ghost"
					size="xs"
					onclick={fit}
					title={irisT("Fit to view", $irisLocale)}
					disabled={!network || loading}
				>
					<MaximizeIcon class="h-3.5 w-3.5" />
				</Button>
				<Button
					variant="ghost"
					size="xs"
					onclick={togglePhysics}
					title={physicsEnabled ? irisT("Freeze layout", $irisLocale) : irisT("Resume physics", $irisLocale)}
					disabled={!network || loading}
				>
					{#if physicsEnabled}
						<PauseIcon class="h-3.5 w-3.5" />
					{:else}
						<PlayIcon class="h-3.5 w-3.5" />
					{/if}
				</Button>
				<Button variant="ghost" size="xs" onclick={() => load(caseId, false)} title={irisT("Refresh graph", $irisLocale)} disabled={loading}>
					<RefreshCwIcon class="h-3.5 w-3.5 {loading ? 'animate-spin' : ''}" />
				</Button>
			</div>
		</div>

		<div class="flex flex-wrap items-center gap-2 border-b px-3 py-2">
			{#if canEdit}
				<Button variant="outline" size="xs" disabled={loading} onclick={() => (edit = { resource: 'nodes' })}>
					{irisT('Add graph node', $irisLocale)}
				</Button>
				<Button variant="outline" size="xs" disabled={loading || graph.nodes.length < 2}
					onclick={() => (edit = { resource: 'edges', source: selectedNodeId ?? undefined })}>
					{irisT('Add connection', $irisLocale)}
				</Button>
			{/if}
			<Button variant={visibleGroups.node ? 'secondary' : 'ghost'} size="xs"
				aria-pressed={visibleGroups.node} onclick={() => toggleGroup('node')}>
				{irisT('Manual nodes', $irisLocale)} {groupCounts.node}
			</Button>
			<div class="ml-auto flex flex-wrap items-center gap-2">
				<select class="max-w-56 rounded-md border bg-background px-2 py-1 text-xs"
					aria-label={irisT('Saved graph views', $irisLocale)} value={activeViewId ?? ''}
					onchange={(e) => {
						const view = graph.views.find((item) => item.id === Number(e.currentTarget.value));
						if (view) void restoreView(view);
					}}>
					<option value="" disabled>{irisT('Saved graph views', $irisLocale)}</option>
					{#each graph.views as view (view.id)}
						<option value={view.id}>{view.label}</option>
					{/each}
				</select>
				{#if activeView}
					<Button variant="ghost" size="xs" disabled={loading} onclick={() => restoreView(activeView)}>
						{irisT('Restore graph view', $irisLocale)}
					</Button>
				{/if}
				{#if canEdit}
					<Button variant="outline" size="xs" disabled={!network || loading}
						onclick={() => (edit = { resource: 'views' })}>{irisT('Save graph view', $irisLocale)}</Button>
					{#if activeView}
						<Button variant="outline" size="xs" disabled={!network || loading}
							onclick={() => (edit = { ...activeView, resource: 'views' })}>
							{irisT('Update graph view', $irisLocale)}
						</Button>
						<Button variant="ghost" size="xs" disabled={loading}
							onclick={() => (edit = { ...activeView, resource: 'views', remove: true })}>
							{irisT('Delete view', $irisLocale)}
						</Button>
					{/if}
				{/if}
			</div>
		</div>

		<!-- Canvas + right details rail. -->
		<div class="relative flex min-h-0 flex-1">
			<div class="relative flex-1 bg-muted/10">
				{#if graphData.nodes.length > 0 && displayedNodes.length > 0}
					<VisNetwork
						nodes={displayedNodes}
						{edges}
						{options}
						className="h-full w-full"
						preservePositions
						onClick={handleClick}
						onContextMenu={openContextMenu}
						onReady={handleReady}
					/>
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
							{irisT("View", $irisLocale)} {contextMenu.node.group}
							{contextMenu.node.label}
						</Button>
					</div>
				{/if}

				{#if loading}
					<div
						class="absolute inset-0 flex items-center justify-center bg-background/40 text-sm text-muted-foreground backdrop-blur-sm"
					>
						<RefreshCwIcon class="mr-2 h-4 w-4 animate-spin" />
						{irisT("Loading graph…", $irisLocale)}
					</div>
				{:else if error}
					<div class="absolute inset-0 flex items-center justify-center text-sm text-destructive">
						{irisT(error, $irisLocale)}
					</div>
				{:else if !graphData.nodes.length}
					<div
						class="absolute inset-0 flex flex-col items-center justify-center gap-1 text-sm text-muted-foreground"
					>
						<div>{irisT("No graph data.", $irisLocale)}</div>
						<div class="text-xs">
							{irisT("Add assets or IOCs to timeline events and enable \"Display in graph\".", $irisLocale)}
						</div>
					</div>
				{:else if displayedNodes.length === 0}
					<div
						class="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
					>
						<div>{irisT("Every node is currently filtered out.", $irisLocale)}</div>
						<Button
							variant="outline"
							size="xs"
							onclick={() => {
								visibleGroups = { asset: true, ioc: true, node: true };
								searchQuery = '';
							}}
						>
							{irisT("Reset filters", $irisLocale)}
						</Button>
					</div>
				{/if}

				<!-- Legend, bottom-left over the canvas. -->
				<div
					class="pointer-events-none absolute bottom-2 left-2 hidden gap-3 rounded-md border bg-background/80 px-3 py-1.5 text-2xs text-muted-foreground shadow-sm backdrop-blur-sm md:flex"
				>
					<span class="inline-flex items-center gap-1">
						<HardDriveIcon class="h-3 w-3" /> {irisT("Asset", $irisLocale)}
					</span>
					<span class="inline-flex items-center gap-1">
						<FingerprintIcon class="h-3 w-3" /> {irisT("IOC", $irisLocale)}
					</span>
				</div>

				{#if graphData.nodes.length > 0 && !hasActiveFilter && !selectedNodeId && !selectedEdgeId}
					<div
						class="pointer-events-none absolute left-2 top-2 max-w-xs rounded-md border bg-background/80 px-2.5 py-1.5 text-2xs text-muted-foreground shadow-sm backdrop-blur-sm"
					>
						{irisT("Select a node or connection to see its details.", $irisLocale)}
					</div>
				{/if}
			</div>

			{#if selectedEdge}
				<aside class="flex w-80 shrink-0 flex-col overflow-hidden border-l bg-card"
					aria-label={irisT('Selected connection details', $irisLocale)}>
					<header class="flex items-start justify-between gap-2 border-b px-4 py-3">
						<div class="min-w-0 text-sm font-medium">
							{#if selectedEdge.label}<div>{selectedEdge.label}</div>{/if}
							{nodeById.get(selectedEdge.source)?.label}
							{selectedEdge.directed ? '→' : '↔'}
							{nodeById.get(selectedEdge.target)?.label}
						</div>
						<Button variant="ghost" size="xs" onclick={() => (selectedEdgeId = null)}
							title={irisT('Close details', $irisLocale)}>
							<XIcon class="h-3.5 w-3.5" />
						</Button>
					</header>
					<div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
						{#if canEdit && selectedEdge.id}
							<div class="mb-3 flex gap-2">
								<Button variant="outline" size="xs" onclick={() => (edit = { ...selectedEdge, resource: 'edges' })}>
									{irisT('Edit connection', $irisLocale)}
								</Button>
								<Button variant="ghost" size="xs" onclick={() => (edit = { ...selectedEdge, resource: 'edges', remove: true })}>
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
									<a class="block rounded border px-2 py-1.5 text-xs hover:bg-muted"
										href={`/case/${caseId}/timeline?event=${event.id}`}>
										{event.title}
										{#if event.date}
											<span class="block text-muted-foreground">{event.date.replace('T', ' ')}</span>
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
					aria-label={irisT("Selected node details", $irisLocale)}
				>
					<header class="flex items-center gap-2 border-b px-4 py-3">
						<div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
							{#if selectedNode.group === 'ioc'}
								<FingerprintIcon class="h-3.5 w-3.5 text-blue-600 dark:text-blue-300" />
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
							title={irisT("Close details", $irisLocale)}
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
									{irisT("Connected nodes", $irisLocale)}
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
									<li class="px-2 py-1.5 text-xs text-muted-foreground">{irisT("No connections.", $irisLocale)}</li>
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
										<Button variant="outline" size="xs" onclick={() => (edit = { ...item, resource: 'nodes' })}>
											{irisT('Edit graph node', $irisLocale)}
										</Button>
										<Button variant="ghost" size="xs" onclick={() => (edit = { ...item, resource: 'nodes', remove: true })}>
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
							{irisT("Open", $irisLocale)} {selectedNode.group}
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
	<GraphEditDialog {edit} nodes={graph.nodes} onSave={saveEdit} onClose={() => (edit = null)} />
{/if}
