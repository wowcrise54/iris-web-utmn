<script lang="ts">
	import { getContext, untrack } from 'svelte';
	import { page } from '$app/state';
	import { CASE_ACCESS_CTX, type CaseAccessContext } from '$lib/contexts/case-access.context.svelte';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { ApiService } from '$lib/services/api.service';
	import { Button } from '$lib/components/ui/button';
	import Input from '$lib/components/ui/input/input.svelte';

	type ItemKind = 'asset' | 'ioc' | 'task' | 'evidence';
	type ItemRef = { kind: ItemKind; id: number };
	type Item = ItemRef & { label: string };
	type ItemResults = { items: Item[]; next_after: number | null };
	type Row = { id?: string; label: string; values: string[]; completed: boolean[]; item?: ItemRef | null };
	type TrackerData = { name: string; columns: string[]; steps: string[]; rows: Row[]; timeline_sync?: boolean };
	type Tracker = TrackerData & { id: number; version: number };

	const locale = useLocale();
	const access = getContext<CaseAccessContext | undefined>(CASE_ACCESS_CTX);
	const canEdit = $derived(access?.canEdit() ?? false);
	const path = $derived(`/api/v2/cases/${page.params.case_id}/trackers`);
	let trackers = $state<Tracker[]>([]);
	let pending = $state(false);
	let error = $state('');
	let showCreate = $state(false);
	let name = $state('');
	let columns = $state('');
	let steps = $state('');
	let dirty = $state<number[]>([]);
	let pickerId = $state<number | null>(null);
	let kind = $state<ItemKind>('asset');
	let query = $state('');
	let results = $state<ItemResults | null>(null);
	let itemPending = $state(false);
	let itemError = $state(false);
	let requestId = 0;
	let submittedQuery = '';

	const itemKinds = {
		asset: { title: 'Assets', route: 'assets' },
		ioc: { title: 'IOCs', route: 'iocs' },
		task: { title: 'Tasks', route: 'tasks' },
		evidence: { title: 'Evidence', route: 'evidence' }
	};

	function messages(response: { status: number; error?: { message: string } }) {
		if (response.status === 409) return 'The tracker has changed. Reload it before editing.';
		if (response.status === 400) return 'Invalid tracker';
		return response.error?.message ?? 'Could not save tracker.';
	}

	function closePicker() {
		pickerId = null;
		requestId++;
	}

	async function findItems(after = 0) {
		const id = ++requestId;
		if (!after) submittedQuery = query.trim();
		const url = ApiService.withQuery(`${path}/items/${kind}`, { query: submittedQuery, after });
		itemPending = true;
		itemError = false;
		try {
			const response = await ApiService.get<ItemResults>(url);
			if (id !== requestId) return;
			if (!response.ok || !response.data || typeof response.data === 'string') {
				itemError = true;
				return;
			}
			const incoming = response.data;
			results = after && results
				? { items: [...results.items, ...incoming.items], next_after: incoming.next_after }
				: incoming;
		} catch {
			if (id === requestId) itemError = true;
		} finally {
			if (id === requestId) itemPending = false;
		}
	}

	function openPicker(tracker: Tracker) {
		pickerId = tracker.id;
		kind = 'asset';
		query = '';
		results = null;
		void findItems();
	}

	async function load(url: string) {
		closePicker();
		pending = true;
		error = '';
		try {
			const result = await ApiService.get<Tracker[]>(url);
			if (url !== path) return;
			if (result.ok && Array.isArray(result.data)) {
				trackers = result.data;
				dirty = [];
			} else {
				error = 'Could not load trackers.';
			}
		} catch {
			if (url === path) error = 'Could not load trackers.';
		} finally {
			if (url === path) pending = false;
		}
	}

	$effect(() => {
		const url = path;
		untrack(() => {
			trackers = [];
			dirty = [];
			showCreate = false;
			name = columns = steps = '';
			void load(url);
		});
	});

	const split = (value: string) => value.split('\n').map((label) => label.trim()).filter(Boolean);
	const markDirty = (id: number) => {
		if (!dirty.includes(id)) dirty.push(id);
	};

	async function save(data: TrackerData, tracker?: Tracker, remove = false) {
		const url = path;
		const target = tracker ? `${url}/${tracker.id}/${tracker.version}` : url;
		pending = true;
		error = '';
		try {
			const result = remove
				? await ApiService.delete<Tracker>(target)
				: tracker
					? await ApiService.put<Tracker>(target, data)
					: await ApiService.post<Tracker>(target, data);
			if (url !== path) return;
			if (!result.ok) {
				error = messages(result);
				return;
			}
			if (remove) {
				trackers = trackers.filter((item) => item.id !== tracker?.id);
				if (pickerId === tracker?.id) closePicker();
			} else if (result.data && typeof result.data === 'object') {
				const saved = result.data;
				trackers = tracker
					? trackers.map((item) => item.id === tracker.id ? saved : item)
					: [...trackers, saved];
			}
			if (tracker) {
				dirty = dirty.filter((id) => id !== tracker.id);
			} else {
				showCreate = false;
				name = columns = steps = '';
			}
		} catch {
			if (url === path) error = 'Could not save tracker.';
		} finally {
			if (url === path) pending = false;
		}
	}

	function addRow(tracker: Tracker, item?: Item) {
		tracker.rows.push({
			label: item?.label ?? '',
			values: tracker.columns.map(() => ''),
			completed: tracker.steps.map(() => false),
			item: item ? { kind: item.kind, id: item.id } : null
		});
		markDirty(tracker.id);
	}

	function isLinked(tracker: Tracker, item: ItemRef) {
		return tracker.rows.some((row) => row.item?.kind === item.kind && row.item.id === item.id);
	}
</script>

<div class="flex flex-col gap-4 p-4">
	<div class="flex flex-wrap items-center justify-between gap-2">
		<h1 class="text-xl font-semibold">{irisT('Response trackers', $locale)}</h1>
		<div class="flex gap-2">
			<Button variant="outline" disabled={pending} onclick={() => {
				if (!dirty.length || confirm(irisT('Reload trackers and discard local edits?', $locale))) void load(path);
			}}>{irisT('Refresh', $locale)}</Button>
			{#if canEdit}
				<Button disabled={pending} onclick={() => (showCreate = !showCreate)}>
					{irisT('New tracker', $locale)}
				</Button>
			{/if}
		</div>
	</div>

	{#if error}
		<p role="alert" class="text-sm text-destructive">{irisT(error, $locale)}</p>
	{/if}

	{#if showCreate && canEdit}
		<form class="grid max-w-2xl gap-3 rounded-md border p-4" onsubmit={(event) => {
			event.preventDefault();
			void save({ name, columns: split(columns), steps: split(steps), rows: [] });
		}}>
			<label class="grid gap-1">
				{irisT('Tracker name', $locale)}
				<Input required maxlength={128} bind:value={name} disabled={pending} />
			</label>
			<label class="grid gap-1">
				{irisT('Columns (one per line)', $locale)}
				<textarea class="rounded-md border bg-background p-2" bind:value={columns} disabled={pending}></textarea>
			</label>
			<label class="grid gap-1">
				{irisT('Steps (one per line)', $locale)}
				<textarea class="rounded-md border bg-background p-2" bind:value={steps} disabled={pending} required></textarea>
			</label>
			<Button type="submit" class="justify-self-start" disabled={pending}>{irisT('Create', $locale)}</Button>
		</form>
	{/if}

	{#if !pending && !error && !trackers.length}
		<p class="text-sm text-muted-foreground">{irisT('No response trackers', $locale)}</p>
	{/if}

	{#each trackers as tracker (tracker.id)}
		<form class="grid gap-3 rounded-md border p-4" onsubmit={(event) => {
			event.preventDefault();
			const { name, columns, steps, rows, timeline_sync } = tracker;
			void save({ name, columns, steps, rows, timeline_sync }, tracker);
		}}>
			{#if canEdit}
				<Input class="max-w-80 font-semibold" aria-label={irisT('Tracker name', $locale)}
					required maxlength={128} bind:value={tracker.name} disabled={pending}
					oninput={() => markDirty(tracker.id)} />
			{:else}
				<h2 class="font-semibold">{tracker.name}</h2>
			{/if}
			{#if canEdit || tracker.timeline_sync}
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={tracker.timeline_sync} disabled={pending || !canEdit}
						onchange={() => markDirty(tracker.id)} />
					{irisT('Record step changes in the case timeline', $locale)}
				</label>
			{/if}
			<div class="overflow-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="border-b text-start">
							<th scope="col" class="p-2 text-start">{irisT('Item', $locale)}</th>
							{#each tracker.columns as column}
								<th scope="col" class="p-2 text-start">{column}</th>
							{/each}
							{#each tracker.steps as step}
								<th scope="col" class="p-2 text-start">{step}</th>
							{/each}
							{#if canEdit}<th scope="col"><span class="sr-only">{irisT('Actions', $locale)}</span></th>{/if}
						</tr>
					</thead>
					<tbody>
						{#each tracker.rows as row, rowIndex}
							<tr class="border-b">
								<td class="min-w-32 p-2">
									{#if canEdit}
										<Input aria-label={irisT('Item', $locale)} required maxlength={128}
											bind:value={row.label} disabled={pending} oninput={() => markDirty(tracker.id)} />
									{:else}
										{row.label}
									{/if}
									{#if row.item}
										<a class="text-xs text-primary underline"
											href={`/case/${page.params.case_id}/${itemKinds[row.item.kind].route}/${row.item.id}`}>
											{irisT(itemKinds[row.item.kind].title, $locale)} #{row.item.id}
										</a>
									{/if}
								</td>
								{#each tracker.columns as column, index}
									<td class="min-w-24 p-2">
										{#if canEdit}
											<Input aria-label={column} maxlength={512} bind:value={row.values[index]}
												disabled={pending} oninput={() => markDirty(tracker.id)} />
										{:else}
											{row.values[index]}
										{/if}
									</td>
								{/each}
								{#each tracker.steps as step, index}
									<td class="p-2 text-center">
										<input type="checkbox" aria-label={step} bind:checked={row.completed[index]}
											disabled={pending || !canEdit} onchange={() => markDirty(tracker.id)} />
									</td>
								{/each}
								{#if canEdit}
									<td class="p-2">
										<Button type="button" variant="ghost" disabled={pending} onclick={() => {
											tracker.rows.splice(rowIndex, 1);
											markDirty(tracker.id);
										}}>{irisT('Remove', $locale)}</Button>
									</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if canEdit}
				<div class="flex flex-wrap gap-2">
					<Button type="button" variant="outline" disabled={pending || tracker.rows.length >= 200}
						onclick={() => addRow(tracker)}>{irisT('Add row', $locale)}</Button>
					<Button type="button" variant="outline" disabled={pending || tracker.rows.length >= 200}
						onclick={() => pickerId === tracker.id ? closePicker() : openPicker(tracker)}>
						{irisT('Link case item', $locale)}
					</Button>
					<Button type="submit" disabled={pending || !dirty.includes(tracker.id)}>{irisT('Save', $locale)}</Button>
					<Button type="button" variant="outline" disabled={pending} onclick={() => {
						if (confirm(irisT('Delete this tracker and all its rows?', $locale))) void save(tracker, tracker, true);
					}}>{irisT('Delete', $locale)}</Button>
				</div>
				{#if pickerId === tracker.id}
					<div class="grid gap-2 rounded border p-3">
						<div class="flex flex-wrap gap-2">
							<select class="rounded border bg-background px-2" aria-label={irisT('Type', $locale)}
								bind:value={kind} onchange={() => { results = null; void findItems(); }}>
								{#each Object.entries(itemKinds) as [value, config]}
									<option {value}>{irisT(config.title, $locale)}</option>
								{/each}
							</select>
							<Input class="w-64" aria-label={irisT('Search', $locale)} maxlength={128}
								bind:value={query} onkeydown={(event) => {
									if (event.key === 'Enter') {
										event.preventDefault();
										results = null;
										void findItems();
									}
								}} />
							<Button type="button" variant="outline" disabled={itemPending}
								onclick={() => { results = null; void findItems(); }}>{irisT('Search', $locale)}</Button>
						</div>
						{#if itemError}
							<p role="alert">{irisT('Could not load case items.', $locale)}</p>
						{:else if !itemPending && results?.items.length === 0}
							<p class="text-sm text-muted-foreground">{irisT('No results', $locale)}</p>
						{/if}
						<div class="flex max-h-48 flex-col items-start overflow-auto">
							{#each results?.items ?? [] as item (item.id)}
								<Button type="button" variant="ghost" disabled={pending || isLinked(tracker, item) || tracker.rows.length >= 200}
									onclick={() => addRow(tracker, item)}>{item.label} #{item.id}</Button>
							{/each}
						</div>
						{#if results?.next_after}
							{@const after = results.next_after}
							<Button type="button" variant="outline" class="justify-self-start" disabled={itemPending}
								onclick={() => void findItems(after)}>{irisT('Load more', $locale)}</Button>
						{/if}
					</div>
				{/if}
			{/if}
		</form>
	{/each}
</div>
