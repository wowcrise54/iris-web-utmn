<script lang="ts">
	import { translate, useLocale } from '$lib/i18n/context';
	import { Button } from '$lib/components/ui/button';
	import { ApiService } from '$lib/services/api.service';

	type Path = { node_keys: string[]; edge_keys: string[] };
	let {
		caseId,
		nodes,
		includes,
		onHighlight
	}: {
		caseId: number;
		nodes: { id: string; label: string }[];
		includes: string[];
		onHighlight: (keys: string[]) => void;
	} = $props();

	const locale = useLocale();
	const t = (key: string) => translate(key, $locale);
	let source = $state('');
	let target = $state('');
	let directed = $state(true);
	let busy = $state(false);
	let paths = $state<Path[] | null>(null);
	let selected = $state(-1);
	let error = $state(false);
	const labels = $derived(new Map(nodes.map((node) => [node.id, node.label])));
	let requestVersion = 0;

	function clear() {
		requestVersion++;
		busy = false;
		paths = null;
		selected = -1;
		error = false;
		onHighlight([]);
	}

	function select(path: Path, index: number) {
		selected = index;
		onHighlight([...path.node_keys, ...path.edge_keys]);
	}

	async function find() {
		clear();
		const version = requestVersion;
		busy = true;
		try {
			const url = ApiService.withQuery(`/cases/${caseId}/graph/paths`, {
				source,
				target,
				directed,
				include: includes.join(',')
			});
			const response = await ApiService.get<{ paths: Path[] }>(url);
			if (version !== requestVersion) return;
			const data = response.data;
			if (!response.ok || !data || typeof data === 'string') {
				error = true;
				return;
			}
			paths = data.paths;
			if (data.paths.length) select(data.paths[0], 0);
		} catch {
			if (version === requestVersion) error = true;
		} finally {
			if (version === requestVersion) busy = false;
		}
	}

	$effect(() => () => {
		requestVersion++;
	});
</script>

<form
	class="flex flex-wrap items-end gap-2 border-b px-3 py-2"
	onsubmit={(event) => {
		event.preventDefault();
		void find();
	}}
>
	<label class="grid gap-1 text-xs">
		{t('Source')}
		<select class="max-w-52 rounded border bg-background p-1" bind:value={source} onchange={clear}>
			<option value="">{t('Select a node')}</option>
			{#each nodes as node (node.id)}
				<option value={node.id}>{node.label} ({node.id})</option>
			{/each}
		</select>
	</label>
	<label class="grid gap-1 text-xs">
		{t('Target')}
		<select class="max-w-52 rounded border bg-background p-1" bind:value={target} onchange={clear}>
			<option value="">{t('Select a node')}</option>
			{#each nodes as node (node.id)}
				<option value={node.id}>{node.label} ({node.id})</option>
			{/each}
		</select>
	</label>
	<label class="flex items-center gap-1 px-1 py-2 text-xs">
		<input type="checkbox" bind:checked={directed} onchange={clear} />
		{t('Follow connection direction')}
	</label>
	<Button
		type="submit"
		size="xs"
		disabled={busy || !labels.has(source) || !labels.has(target) || source === target}
	>
		{t('Find paths')}
	</Button>
	{#if error}
		<p role="alert" class="text-xs text-destructive">{t('Could not find graph paths')}</p>
	{:else if paths?.length === 0}
		<p role="status" class="text-xs">{t('No path found')}</p>
	{:else if paths?.length}
		<div class="flex max-w-full flex-wrap gap-1">
			{#each paths as path, index}
				<Button
					type="button"
					size="xs"
					variant={index === selected ? 'secondary' : 'ghost'}
					aria-pressed={index === selected}
					onclick={() => select(path, index)}
				>
					{path.node_keys.map((key) => labels.get(key) ?? key).join(' → ')}
				</Button>
			{/each}
		</div>
	{/if}
</form>
