<script lang="ts">
	import { translate as t, useLocale } from '$lib/i18n/context';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import type { GraphEdit, GraphNode } from './types';

	let { edit, nodes, onSave, onClose }: {
		edit: GraphEdit;
		nodes: GraphNode[];
		onSave: (edit: GraphEdit, body: Record<string, unknown>) => Promise<boolean>;
		onClose: () => void;
	} = $props();

	const locale = useLocale();
	let label = $state('');
	let description = $state('');
	let source = $state('');
	let target = $state('');
	let directed = $state(true);
	let eventIds = $state('');
	let saving = $state(false);
	let error = $state('');

	$effect(() => {
		label = edit.label ?? '';
		description = edit.description ?? '';
		source = edit.source ?? '';
		target = edit.target ?? '';
		directed = edit.directed ?? true;
		eventIds = edit.event_ids?.join(', ') ?? '';
		error = '';
	});

	const title = $derived(edit.remove ? 'Delete graph item' : {
		nodes: edit.id ? 'Edit graph node' : 'Add graph node',
		edges: edit.id ? 'Edit connection' : 'Add connection',
		views: edit.id ? 'Update graph view' : 'Save graph view'
	}[edit.resource]);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (saving) return;
		const body: Record<string, unknown> = { label: label.trim() };
		if (!edit.remove && edit.resource === 'nodes') body.description = description;
		if (!edit.remove && edit.resource === 'edges') {
			const ids = eventIds.trim() ? eventIds.trim().split(/[\s,]+/).map(Number) : [];
			if (!source || !target || source === target || ids.some((id) => !Number.isSafeInteger(id) || id < 1)) {
				error = 'Choose two distinct nodes and enter valid event IDs.';
				return;
			}
			Object.assign(body, { source, target, directed, event_ids: [...new Set(ids)] });
		}
		saving = true;
		error = '';
		try {
			if (await onSave(edit, body)) onClose();
			else error = 'Could not save graph changes.';
		} finally {
			saving = false;
		}
	}
</script>

<Dialog.Root open={true} onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
	<Dialog.Content class="max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{t(title, $locale)}</Dialog.Title>
		</Dialog.Header>
		<form class="space-y-3" onsubmit={submit}>
			{#if edit.remove}
				<p class="break-words text-sm">{edit.label}</p>
				{#if edit.resource === 'nodes'}
					<p class="text-sm text-muted-foreground">{t('Connections to this node will also be deleted.', $locale)}</p>
				{/if}
			{:else}
				<label class="block space-y-1 text-sm">
					<span>{t('Name', $locale)}</span>
					<input class="w-full rounded-md border bg-background px-2 py-1" bind:value={label}
						required minlength="1" maxlength="200" />
				</label>
				{#if edit.resource === 'nodes'}
					<label class="block space-y-1 text-sm">
						<span>{t('Description', $locale)}</span>
						<textarea class="w-full rounded-md border bg-background px-2 py-1" bind:value={description}
							maxlength="10000" rows="3"></textarea>
					</label>
				{:else if edit.resource === 'edges'}
					{#snippet endpoints()}
						<option value="" disabled>{t('Select a node', $locale)}</option>
						{#each nodes as node (node.key)}
							<option value={node.key}>{node.label} ({node.key})</option>
						{/each}
					{/snippet}
					<label class="block space-y-1 text-sm">
						<span>{t('Source', $locale)}</span>
						<select class="w-full rounded-md border bg-background px-2 py-1" aria-label={t('Source', $locale)} bind:value={source} required>
							{@render endpoints()}
						</select>
					</label>
					<label class="block space-y-1 text-sm">
						<span>{t('Target', $locale)}</span>
						<select class="w-full rounded-md border bg-background px-2 py-1" aria-label={t('Target', $locale)} bind:value={target} required>
							{@render endpoints()}
						</select>
					</label>
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={directed} /> {t('Directed connection', $locale)}
					</label>
					<label class="block space-y-1 text-sm">
						<span>{t('Supporting event IDs', $locale)}</span>
						<input class="w-full rounded-md border bg-background px-2 py-1" bind:value={eventIds}
							placeholder="101, 102" maxlength="10000" />
					</label>
				{/if}
			{/if}
			{#if error}<p class="text-sm text-destructive" role="alert">{t(error, $locale)}</p>{/if}
			<div class="flex justify-end gap-2">
				<Button type="button" variant="outline" disabled={saving} onclick={onClose}>{t('Cancel', $locale)}</Button>
				<Button type="submit" variant={edit.remove ? 'destructive' : 'default'} disabled={saving}>
					{t(edit.remove ? 'Delete' : 'Save', $locale)}
				</Button>
			</div>
		</form>
	</Dialog.Content>
</Dialog.Root>
