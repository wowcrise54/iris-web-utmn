<!--
  Investigation graph relation types (§4.9).

  The catalogue of relations analysts draw between assets, IOCs and free
  nodes (`lateral_movement`, `beacons_to`…), with the colour, line style
  and direction the graph renders them with, and the STIX relationship
  they export as. Same master/detail chrome as the asset flags: ordered
  list on the left (drag or up/down to reorder — the order of the
  relation pickers), details on the right, one dialog for add/edit.

  Built-in types keep their name and cannot be deleted; a type used by
  stored relations cannot be deleted either. Admin only: the nav entry is
  gated on `server_administrator` and every mutation is re-checked by the
  backend.
-->
<script lang="ts">
    import { translate as irisT, useLocale } from '$lib/i18n/context';
    const irisLocale = useLocale();
	import { onMount } from 'svelte';
	import { mode } from 'mode-watcher';
	import {
		ChevronDownIcon,
		ChevronUpIcon,
		GripVerticalIcon,
		LockIcon,
		MoveRightIcon,
		MinusIcon,
		PencilIcon,
		PlusIcon,
		RefreshCwIcon,
		SplineIcon,
		Trash2Icon
	} from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Switch } from '$lib/components/ui/switch';
	import { Textarea } from '$lib/components/ui/textarea';
	import { toast } from '$lib/components/ui/toast';
	import ConfirmationDialog from '$lib/components/ui/dialog/ConfirmationDialog.svelte';
	import FlagColorPicker from '$lib/components/common/assets/FlagColorPicker.svelte';
	import { paletteHex } from '$lib/components/common/CytoscapeGraph/palette';
	import { GraphRelationTypesService } from '$lib/services/graph-relation-types.service';
	import type { GraphLineStyle, GraphRelationType } from '$lib/types/resources/case-graph';
	import {
		RELATION_DESCRIPTION_MAX,
		RELATION_LABEL_MAX,
		RELATION_LINE_STYLES,
		blankRelationTypeForm,
		moveItem,
		relationNameFromLabel,
		relationTypeBody,
		relationTypeDeleteBlocker,
		relationTypeToForm,
		sortRelationTypes,
		validateRelationTypeForm,
		type RelationTypeForm
	} from '$lib/utils/graph-relation-types';

	let types = $state<GraphRelationType[]>([]);
	let loading = $state(false);
	let reordering = $state(false);
	let selectedId = $state<number | null>(null);
	const selected = $derived(types.find((t) => t.id === selectedId) ?? null);
	const isDark = $derived($mode === 'dark');

	// Add / edit dialog -------------------------------------------------
	let editorOpen = $state(false);
	let editorBusy = $state(false);
	let editorError = $state<string | null>(null);
	let editing = $state<GraphRelationType | null>(null);
	let form = $state<RelationTypeForm>(blankRelationTypeForm());
	// Creating: the name follows the label until it is edited by hand.
	let nameTouched = $state(false);

	// Delete confirmation -----------------------------------------------
	let confirmOpen = $state(false);
	let confirmTarget = $state<GraphRelationType | null>(null);

	const showError = (msg: string | null | undefined, fallback = 'Operation failed') =>
		toast({ title: irisT(msg || fallback, $irisLocale), variant: 'destructive' });
	const showSuccess = (msg: string) => toast({ title: irisT(msg, $irisLocale), variant: 'success' });

	const errorOf = (res: { data?: unknown; error?: { message?: string } }): string | undefined => {
		const data = res.data as { message?: string } | null | undefined;
		return (data && typeof data === 'object' ? data.message : undefined) ?? res.error?.message;
	};

	const plural = (n: number) => `${n} ${irisT('Connections', $irisLocale)}`;

	const stroke = (style: GraphLineStyle, color: string) =>
		`border-top: 2px ${style} ${paletteHex(color, isDark)};`;

	const applyList = (items: GraphRelationType[]) => {
		types = sortRelationTypes(items);
		if (selectedId === null || !types.some((t) => t.id === selectedId)) {
			selectedId = types[0]?.id ?? null;
		}
	};

	const loadList = async () => {
		loading = true;
		try {
			const res = await GraphRelationTypesService.listRelationTypes();
			if (res.ok && Array.isArray(res.data)) applyList(res.data);
			else showError(errorOf(res), 'Failed to load the relation types');
		} catch (e) {
			showError((e as Error).message);
		} finally {
			loading = false;
		}
	};

	onMount(loadList);

	// Reorder -------------------------------------------------------------
	const persistOrder = async (next: GraphRelationType[]) => {
		const previous = types;
		types = next;
		reordering = true;
		try {
			const res = await GraphRelationTypesService.reorderRelationTypes(next.map((t) => t.id));
			if (res.ok && Array.isArray(res.data)) {
				applyList(res.data);
			} else {
				types = previous;
				showError(errorOf(res), 'Unable to reorder the relation types');
			}
		} catch (e) {
			types = previous;
			showError((e as Error).message);
		} finally {
			reordering = false;
		}
	};

	const move = (from: number, to: number) => {
		if (reordering || from === to || to < 0 || to >= types.length) return;
		void persistOrder(moveItem(types, from, to));
	};

	let dragIndex = $state<number | null>(null);
	let dropIndex = $state<number | null>(null);

	const onDragStart = (e: DragEvent, index: number) => {
		dragIndex = index;
		if (e.dataTransfer) {
			e.dataTransfer.effectAllowed = 'move';
			e.dataTransfer.setData('text/plain', `${types[index]?.id ?? ''}`);
		}
	};

	const onDragOver = (e: DragEvent, index: number) => {
		if (dragIndex === null) return;
		e.preventDefault();
		if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
		dropIndex = index;
	};

	const onDrop = (e: DragEvent, index: number) => {
		e.preventDefault();
		const from = dragIndex;
		dragIndex = null;
		dropIndex = null;
		if (from !== null) move(from, index);
	};

	const onDragEnd = () => {
		dragIndex = null;
		dropIndex = null;
	};

	// Editor --------------------------------------------------------------
	const openAdd = () => {
		editing = null;
		form = blankRelationTypeForm();
		nameTouched = false;
		editorError = null;
		editorOpen = true;
	};

	const openEdit = (t: GraphRelationType) => {
		editing = t;
		form = relationTypeToForm(t);
		nameTouched = true;
		editorError = null;
		editorOpen = true;
	};

	const onLabelInput = (value: string) => {
		form.label = value;
		if (!editing && !nameTouched) form.name = relationNameFromLabel(value);
	};

	const submitEditor = async () => {
		const others = types.filter((t) => t.id !== editing?.id);
		const problem = validateRelationTypeForm(form, others);
		if (problem) {
			editorError = problem;
			return;
		}
		const body = relationTypeBody(form, editing);
		editorBusy = true;
		editorError = null;
		try {
			const res = editing
				? await GraphRelationTypesService.updateRelationType(editing.id, body)
				: await GraphRelationTypesService.createRelationType(body);
			if (!(res.ok && res.data && typeof res.data === 'object')) {
				editorError = errorOf(res) ?? 'Unable to save';
				return;
			}
			const saved = res.data;
			showSuccess(editing ? 'Relation type saved' : 'Relation type created');
			editorOpen = false;
			await loadList();
			selectedId = saved.id;
		} catch (e) {
			editorError = (e as Error).message;
		} finally {
			editorBusy = false;
		}
	};

	// Delete --------------------------------------------------------------
	const askRemove = (t: GraphRelationType) => {
		if (relationTypeDeleteBlocker(t)) return;
		confirmTarget = t;
		confirmOpen = true;
	};

	const runRemove = async () => {
		const t = confirmTarget;
		if (!t) return;
		const res = await GraphRelationTypesService.deleteRelationType(t.id);
		if (res.ok) {
			showSuccess('Relation type deleted');
			if (selectedId === t.id) selectedId = null;
		} else {
			// Someone may have used it in the meantime: the reload shows the count.
			showError(errorOf(res), 'Unable to delete the relation type');
		}
		await loadList();
	};

	const deleteBlocker = $derived(selected?.is_system
		? irisT('Built-in relation types cannot be deleted', $irisLocale)
		: (selected?.edge_count ?? 0) > 0
			? irisT('In use', $irisLocale) + ' (' + selected?.edge_count + ')'
			: null);
</script>

<svelte:head>
	<title>{irisT("Graph relations", $irisLocale)}</title>
</svelte:head>

<div class="flex h-full w-full flex-col overflow-hidden">
	<header class="flex items-center justify-between gap-3 border-b px-5 py-3">
		<div class="flex items-center gap-2.5">
			<SplineIcon size={18} class="text-muted-foreground" />
			<div class="leading-tight">
				<h1 class="text-sm font-semibold">{irisT("Graph relations", $irisLocale)}</h1>
				<p class="text-2xs text-muted-foreground">{irisT("Relation types analysts draw between objects on the case investigation graph, with how they look and how they export to STIX.", $irisLocale)}</p>
			</div>
		</div>

		<div class="flex items-center gap-1.5">
			<Button variant="outline" size="sm" class="h-7" onclick={loadList} disabled={loading}>
				<RefreshCwIcon size={12} class={`mr-1 ${loading ? 'animate-spin' : ''}`} />{irisT("Refresh", $irisLocale)}</Button>
			<Button size="sm" class="h-7" onclick={openAdd}>
				<PlusIcon size={12} class="mr-1" />{irisT("Add relation type", $irisLocale)}</Button>
		</div>
	</header>

	<div class="flex flex-1 gap-3 overflow-hidden p-4">
		<!-- Ordered list -->
		<section class="flex min-h-0 flex-1 basis-1/2 flex-col overflow-hidden rounded-md border">
			<div class="flex items-baseline gap-2 border-b bg-muted/30 px-3 py-2">
				<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{irisT("Relation types", $irisLocale)}</h2>
				<span class="text-2xs tabular-nums text-muted-foreground">{types.length}</span>
				<span class="ml-auto text-2xs text-muted-foreground">{irisT("Drag to reorder", $irisLocale)}</span>
			</div>

			<div class="flex-1 overflow-y-auto">
				{#if loading && types.length === 0}
					<div class="space-y-1 p-3">
						{#each Array(8) as _}
							<Skeleton class="h-9 w-full" />
						{/each}
					</div>
				{:else if types.length === 0}
					<p class="px-3 py-6 text-center text-xs text-muted-foreground">{irisT("No relation type.", $irisLocale)}</p>
				{:else}
					<ul aria-label={irisT("Graph relation types", $irisLocale)} data-testid="graph-relation-types-list">
						{#each types as t, index (t.id)}
							{@const active = t.id === selectedId}
							<li
								class="group flex items-center gap-2 border-b border-l-[3px] px-2.5 py-2 transition-colors
									{active ? 'border-l-primary bg-primary/10' : 'border-l-transparent hover:bg-muted/40'}
									{dropIndex === index && dragIndex !== index ? 'border-t-2 border-t-primary' : ''}
									{dragIndex === index ? 'opacity-50' : ''}"
								draggable={!reordering}
								ondragstart={(e) => onDragStart(e, index)}
								ondragover={(e) => onDragOver(e, index)}
								ondrop={(e) => onDrop(e, index)}
								ondragend={onDragEnd}
								data-testid="graph-relation-type-row"
							>
								<GripVerticalIcon
									class="h-4 w-4 shrink-0 cursor-grab text-muted-foreground/50"
									aria-hidden="true"
								/>
								<button
									type="button"
									class="flex min-w-0 flex-1 items-center gap-2 text-left"
									onclick={() => (selectedId = t.id)}
									aria-pressed={active}
								>
									<span class="flex w-8 shrink-0 items-center" aria-hidden="true">
										<span class="flex-1" style={stroke(t.line_style, t.color)}></span>
										{#if t.directed}
											<MoveRightIcon
												class="-ml-1.5 h-3 w-3"
												style={`color: ${paletteHex(t.color, isDark)}`}
											/>
										{/if}
									</span>
									<span class="min-w-0 flex-1">
										<span class="block truncate text-xs font-medium">{t.label}</span>
										<span class="block truncate font-mono text-2xs text-muted-foreground">
											{t.name}
										</span>
									</span>
								</button>
								{#if t.is_system}
									<span
										class="inline-flex shrink-0 items-center gap-0.5 rounded bg-muted px-1.5 py-0.5 text-2xs text-muted-foreground"
										title={irisT("Built-in: the name is fixed and the type cannot be deleted", $irisLocale)}
									>
										<LockIcon class="h-2.5 w-2.5" />{irisT("Built-in", $irisLocale)}</span>
								{/if}
								<span class="w-20 shrink-0 text-right text-2xs tabular-nums text-muted-foreground">
									{plural(t.edge_count ?? 0)}
								</span>
								<span
									class="flex shrink-0 flex-col opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100"
								>
									<button
										type="button"
										class="text-muted-foreground hover:text-foreground disabled:opacity-30"
										aria-label={irisT('Move up', $irisLocale) + ' ' + t.label}
										disabled={index === 0 || reordering}
										onclick={() => move(index, index - 1)}
									>
										<ChevronUpIcon size={12} />
									</button>
									<button
										type="button"
										class="text-muted-foreground hover:text-foreground disabled:opacity-30"
										aria-label={irisT('Move down', $irisLocale) + ' ' + t.label}
										disabled={index === types.length - 1 || reordering}
										onclick={() => move(index, index + 1)}
									>
										<ChevronDownIcon size={12} />
									</button>
								</span>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</section>

		<!-- Details -->
		<section class="flex min-h-0 flex-1 basis-1/2 flex-col overflow-hidden rounded-md border">
			<div class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
				<div class="flex items-baseline gap-2">
					<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{irisT("Details", $irisLocale)}</h2>
					{#if selected}
						<span class="text-2xs text-muted-foreground">{selected.label}</span>
					{/if}
				</div>

				{#if selected}
					<div class="flex items-center gap-1.5">
						<Button
							variant="outline"
							size="sm"
							class="h-7"
							onclick={() => selected && openEdit(selected)}
						>
							<PencilIcon size={12} class="mr-1" />{irisT("Edit", $irisLocale)}</Button>
						<span title={deleteBlocker ? irisT(deleteBlocker, $irisLocale) : undefined}>
							<Button
								variant="outline"
								size="sm"
								class="h-7 text-destructive hover:text-destructive"
								disabled={deleteBlocker !== null}
								aria-label={deleteBlocker ? irisT('Delete', $irisLocale) + ' (' + deleteBlocker + ')' : irisT('Delete', $irisLocale)}
								onclick={() => selected && askRemove(selected)}
							>
								<Trash2Icon size={12} class="mr-1" />{irisT("Delete", $irisLocale)}</Button>
						</span>
					</div>
				{/if}
			</div>

			<div class="flex-1 overflow-y-auto">
				{#if !selected}
					<p class="px-3 py-10 text-center text-xs text-muted-foreground">{irisT("Select a relation type on the left to see its details.", $irisLocale)}</p>
				{:else}
					<dl class="grid grid-cols-1 gap-3 p-4 text-xs sm:grid-cols-2">
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Label", $irisLocale)}</dt>
							<dd class="font-medium">{selected.label}</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Name", $irisLocale)}</dt>
							<dd class="font-mono text-2xs">{selected.name}</dd>
						</div>
						<div class="sm:col-span-2">
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Description", $irisLocale)}</dt>
							<dd class="whitespace-pre-wrap">{selected.description || '—'}</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Direction", $irisLocale)}</dt>
							<dd class="flex items-center gap-1">
								{#if selected.directed}
									<MoveRightIcon class="h-3.5 w-3.5" />{irisT('Directed', $irisLocale)} (→)
								{:else}
									<MinusIcon class="h-3.5 w-3.5" />{irisT('Undirected', $irisLocale)}
								{/if}
							</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Line", $irisLocale)}</dt>
							<dd class="flex items-center gap-1.5">
								<span class="w-8" style={stroke(selected.line_style, selected.color)}></span>
								{selected.line_style}, {selected.color}
							</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("STIX relationship", $irisLocale)}</dt>
							<dd class="font-mono text-2xs">{selected.stix_relationship || 'related-to'}</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("In use", $irisLocale)}</dt>
							<dd class="tabular-nums">{plural(selected.edge_count ?? 0)}</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Origin", $irisLocale)}</dt>
							<dd>{irisT(selected.is_system ? 'Built-in' : 'Custom', $irisLocale)}</dd>
						</div>
						<div>
							<dt class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Type ID", $irisLocale)}</dt>
							<dd class="font-mono text-2xs">{selected.id}</dd>
						</div>
					</dl>
					{#if deleteBlocker}
						<p class="mx-4 mb-4 text-2xs text-muted-foreground">
							{deleteBlocker}
						</p>
					{/if}
				{/if}
			</div>
		</section>
	</div>
</div>

<!-- Add / Edit dialog -->
<Dialog.Root bind:open={editorOpen}>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{irisT(editing ? 'Edit relation type' : 'Add relation type', $irisLocale)}</Dialog.Title>
			<Dialog.Description>
				{irisT(editing ? 'Existing connections use the updated type.' : 'New types are added to the end of the list.', $irisLocale)}
			</Dialog.Description>
		</Dialog.Header>

		<div class="flex max-h-[65vh] flex-col gap-3 overflow-y-auto pt-2">
			<div class="flex flex-col gap-1">
				<label for="relation-label" class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Label *", $irisLocale)}</label>
				<Input
					id="relation-label"
					value={form.label}
					oninput={(e) => onLabelInput((e.target as HTMLInputElement).value)}
					maxlength={RELATION_LABEL_MAX}
					placeholder={irisT("Lateral movement", $irisLocale)}
					disabled={editorBusy}
				/>
			</div>

			<div class="flex flex-col gap-1">
				<label for="relation-name" class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Name *", $irisLocale)}</label>
				<Input
					id="relation-name"
					class="font-mono"
					value={form.name}
					oninput={(e) => {
						form.name = (e.target as HTMLInputElement).value;
						nameTouched = true;
					}}
					maxlength={64}
					placeholder="lateral_movement"
					disabled={editorBusy || editing?.is_system === true}
				/>
				<span class="text-2xs text-muted-foreground">
					{irisT(editing?.is_system ? 'Built-in types keep their name.' : 'Use lower case letters, digits and underscores for the identifier.', $irisLocale)}
				</span>
			</div>

			<div class="flex flex-col gap-1">
				<label
					for="relation-description"
					class="text-2xs uppercase tracking-wide text-muted-foreground"
				>{irisT("Description", $irisLocale)}</label>
				<Textarea
					id="relation-description"
					rows={2}
					bind:value={form.description}
					maxlength={RELATION_DESCRIPTION_MAX}
					placeholder={irisT("When to use this relation", $irisLocale)}
					disabled={editorBusy}
				/>
			</div>

			<div class="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
				<label for="relation-directed" class="min-w-0">
					<span class="block text-xs font-medium">{irisT("Directed", $irisLocale)}</span>
					<span class="block text-2xs text-muted-foreground">{irisT("Drawn with an arrow from the source to the target.", $irisLocale)}</span>
				</label>
				<Switch id="relation-directed" bind:checked={form.directed} disabled={editorBusy} />
			</div>

			<div class="flex flex-col gap-1">
				<span
					id="relation-color-label"
					class="text-2xs uppercase tracking-wide text-muted-foreground"
				>{irisT("Colour", $irisLocale)}</span>
				<FlagColorPicker
					bind:value={form.color}
					disabled={editorBusy}
					labelledby="relation-color-label"
				/>
			</div>

			<div class="flex flex-col gap-1">
				<span
					id="relation-line-label"
					class="text-2xs uppercase tracking-wide text-muted-foreground"
				>{irisT("Line style", $irisLocale)}</span>
				<div class="grid grid-cols-3 gap-2" role="radiogroup" aria-labelledby="relation-line-label">
					{#each RELATION_LINE_STYLES as ls (ls.value)}
						<button
							type="button"
							role="radio"
							aria-checked={form.line_style === ls.value}
							disabled={editorBusy}
							onclick={() => (form.line_style = ls.value)}
							class="flex items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors {form.line_style ===
							ls.value
								? 'border-primary bg-primary/5'
								: 'hover:bg-muted/40'}"
						>
							<span class="w-6" style={stroke(ls.value, form.color)}></span>
							{irisT(ls.label, $irisLocale)}
						</button>
					{/each}
				</div>
			</div>

			<div class="flex flex-col gap-1">
				<label for="relation-stix" class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("STIX relationship", $irisLocale)}</label>
				<Input
					id="relation-stix"
					class="font-mono"
					bind:value={form.stix_relationship}
					maxlength={64}
					placeholder="related-to"
					disabled={editorBusy}
				/>
				<span class="text-2xs text-muted-foreground">
					<code>relationship_type</code>{irisT("of the STIX 2.1 export (e.g.", $irisLocale)}<code>communicates-with</code>,
					<code>{irisT("uses", $irisLocale)}</code>).
				</span>
			</div>

			<div class="flex items-center gap-2 text-2xs text-muted-foreground">{irisT("Preview", $irisLocale)}<span
					class="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-foreground"
				>
					A
					<span class="flex w-12 items-center">
						<span class="flex-1" style={stroke(form.line_style, form.color)}></span>
						{#if form.directed}
							<MoveRightIcon
								class="-ml-1.5 h-3 w-3"
								style={`color: ${paletteHex(form.color, isDark)}`}
							/>
						{/if}
					</span>
					B
					<span class="ml-1 text-muted-foreground">{form.label.trim() || irisT('Connection', $irisLocale)}</span>
				</span>
			</div>

			{#if editorError}
				<p class="text-2xs text-destructive" role="alert">{irisT(editorError, $irisLocale)}</p>
			{/if}
		</div>

		<Dialog.Footer class="pt-3">
			<Button variant="outline" onclick={() => (editorOpen = false)} disabled={editorBusy}>{irisT("Cancel", $irisLocale)}</Button>
			<Button onclick={submitEditor} disabled={editorBusy}>
				{irisT(editorBusy ? 'Saving…' : editing ? 'Save' : 'Create', $irisLocale)}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>

<ConfirmationDialog
	bind:open={confirmOpen}
	title={irisT('Delete relation type', $irisLocale) + ' «' + (confirmTarget?.label ?? '') + '»?'}
	message={irisT("No stored relation uses it, so it only disappears from the relation pickers. This cannot be undone.", $irisLocale)}
	confirmText={irisT("Delete", $irisLocale)}
	onConfirm={runRemove}
/>
