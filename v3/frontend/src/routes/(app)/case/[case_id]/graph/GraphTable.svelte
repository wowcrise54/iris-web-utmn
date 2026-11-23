<script lang="ts">
	import { translate, useLocale } from '$lib/i18n/context';
	import { Button } from '$lib/components/ui/button';

	type Row = { id: string; cells: string[] };
	let {
		nodes,
		edges,
		selectedNode,
		selectedEdge,
		onSelect,
		onLocate
	}: {
		nodes: Row[];
		edges: Row[];
		selectedNode: string | null;
		selectedEdge: string | null;
		onSelect: (detail: { nodeId?: string; edgeId?: string }) => void;
		onLocate: (kind: 'nodes' | 'edges', ids: string[]) => void;
	} = $props();

	const locale = useLocale();
	const t = (key: string) => translate(key, $locale);
	const pageSize = 50;
	let kind = $state<'nodes' | 'edges'>('nodes');
	let filter = $state('');
	let column = $state(0);
	let descending = $state(false);
	let page = $state(0);
	let checked = $state(new Set<string>());
	const columns = $derived(
		kind === 'nodes' ? ['Name', 'Type'] : ['Source', 'Connection type', 'Target']
	);
	const filtered = $derived.by(() => {
		const search = filter.trim().toLocaleLowerCase();
		return (kind === 'nodes' ? nodes : edges)
			.filter(
				(row) => !search || row.cells.some((cell) => cell.toLocaleLowerCase().includes(search))
			)
			.sort(
				(a, b) =>
					a.cells[column].localeCompare(b.cells[column], undefined, { numeric: true }) *
					(descending ? -1 : 1)
			);
	});
	const pages = $derived(Math.max(1, Math.ceil(filtered.length / pageSize)));
	const currentPage = $derived(Math.min(page, pages - 1));
	const visible = $derived(filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize));
	const selectedRows = $derived(filtered.filter((row) => checked.has(row.id)));
	const pageChecked = $derived(visible.length > 0 && visible.every((row) => checked.has(row.id)));

	function setChecked(ids: string[], value: boolean) {
		const next = new Set(checked);
		for (const id of ids) {
			if (value) next.add(id);
			else next.delete(id);
		}
		checked = next;
	}

	function changeKind(next: typeof kind) {
		kind = next;
		column = 0;
		descending = false;
		page = 0;
		checked = new Set();
	}

	function sortBy(index: number) {
		descending = column === index && !descending;
		column = index;
		page = 0;
	}
</script>

<section
	aria-label={t('Graph as tables')}
	class="absolute inset-0 z-20 flex min-h-0 flex-col bg-background text-sm"
>
	<div class="flex flex-wrap items-center gap-2 border-b p-2">
		<Button
			size="xs"
			aria-pressed={kind === 'nodes'}
			variant={kind === 'nodes' ? 'secondary' : 'ghost'}
			onclick={() => changeKind('nodes')}>{t('Nodes')}</Button
		>
		<Button
			size="xs"
			aria-pressed={kind === 'edges'}
			variant={kind === 'edges' ? 'secondary' : 'ghost'}
			onclick={() => changeKind('edges')}>{t('Connections')}</Button
		>
		<input
			type="search"
			class="rounded border bg-background px-2 py-1 text-xs"
			aria-label={t('Filter rows')}
			placeholder={t('Filter rows')}
			bind:value={filter}
			oninput={() => {
				page = 0;
				checked = new Set();
			}}
		/>
		{#if selectedRows.length}
			<Button
				size="xs"
				onclick={() =>
					onLocate(
						kind,
						selectedRows.map((row) => row.id)
					)}
			>
				{t('Locate on graph')} ({selectedRows.length})
			</Button>
			<Button size="xs" variant="ghost" onclick={() => (checked = new Set())}>
				{t('Clear selection')}
			</Button>
		{/if}
	</div>
	<div class="min-h-0 flex-1 overflow-auto">
		<table class="w-full text-left">
			<caption class="sr-only">{t(kind === 'nodes' ? 'Nodes' : 'Connections')}</caption>
			<thead class="sticky top-0 bg-muted">
				<tr>
					<th scope="col" class="w-8 px-3">
						<input
							type="checkbox"
							aria-label={t('Select rows on this page')}
							checked={pageChecked}
							disabled={!visible.length}
							onchange={(event) =>
								setChecked(
									visible.map((row) => row.id),
									event.currentTarget.checked
								)}
						/>
					</th>
					{#each columns as label, index (label)}
						<th
							scope="col"
							aria-sort={column === index ? (descending ? 'descending' : 'ascending') : undefined}
						>
							<button
								type="button"
								class="w-full px-3 py-2 text-left"
								onclick={() => sortBy(index)}
							>
								{t(label)}{column === index ? (descending ? ' ↓' : ' ↑') : ''}
							</button>
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each visible as row (row.id)}
					<tr class="border-b">
						<td class="px-3">
							<input
								type="checkbox"
								aria-label={t('Select row') + ' · ' + row.cells.join(' · ')}
								checked={checked.has(row.id)}
								onchange={(event) => setChecked([row.id], event.currentTarget.checked)}
							/>
						</td>
						{#each row.cells as cell, index}
							<td class="max-w-64 break-words px-3 py-2">
								{#if index === 0}
									<button
										type="button"
										class="text-left font-medium underline-offset-2 hover:underline"
										aria-pressed={row.id === (kind === 'nodes' ? selectedNode : selectedEdge)}
										aria-label={row.cells.join(' · ')}
										onclick={() =>
											onSelect(kind === 'nodes' ? { nodeId: row.id } : { edgeId: row.id })}
									>
										{cell}
									</button>
								{:else}
									{cell}
								{/if}
							</td>
						{/each}
					</tr>
				{:else}
					<tr
						><td colspan={columns.length + 1} class="p-3 text-muted-foreground"
							>{t('No matching rows')}</td
						></tr
					>
				{/each}
			</tbody>
		</table>
	</div>
	{#if pages > 1}
		<div class="flex items-center gap-2 border-t p-2">
			<Button
				size="xs"
				variant="outline"
				disabled={currentPage === 0}
				onclick={() => (page = currentPage - 1)}>{t('Previous')}</Button
			>
			<span role="status" class="text-xs">{currentPage + 1} / {pages}</span>
			<Button
				size="xs"
				variant="outline"
				disabled={currentPage + 1 >= pages}
				onclick={() => (page = currentPage + 1)}>{t('Next')}</Button
			>
		</div>
	{/if}
</section>
