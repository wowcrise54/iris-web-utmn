<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { getContext } from 'svelte';
	import { RotateCwIcon, SaveIcon } from 'lucide-svelte';
	import {
		CASE_DATASTORE_CTX,
		type CaseDatastoreContext
	} from '$lib/contexts/case-datastore.context.svelte';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { toast } from '$lib/stores/toast.store';

	type Props = {
		open: boolean;
		onOpenChange: (open: boolean) => void;
	};

	let { open = $bindable(), onOpenChange }: Props = $props();

	const datastore = getContext<CaseDatastoreContext>(CASE_DATASTORE_CTX);

	let folderName = $state('');
	let isSaving = $state(false);

	const close = () => onOpenChange(false);

	const parentId = $derived(datastore.ui.selectedFolderId ?? datastore.tree.rootId);

	const save = async () => {
		if (!folderName.trim()) {
			toast({ title: irisT("Folder name is required", $irisLocale), variant: 'destructive' });
			return;
		}
		if (parentId == null) {
			toast({ title: irisT("No parent folder", $irisLocale), variant: 'destructive' });
			return;
		}

		isSaving = true;
		try {
			const created = await datastore.createFolder({
				parent_node: parentId,
				folder_name: folderName.trim()
			});
			if (!created) throw new Error('Failed to create folder');
			toast({ title: irisT("Folder created", $irisLocale), variant: 'success' });
			close();
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Unknown error';
			toast({ title: irisT("Create failed", $irisLocale), description: message, variant: 'destructive' });
		} finally {
			isSaving = false;
		}
	};

	$effect(() => {
		if (!open) {
			folderName = '';
			isSaving = false;
		}
	});
</script>

<Dialog.Root bind:open onOpenChange={(next) => (!next ? close() : null)}>
	<Dialog.Content class="max-w-[480px]">
		<Dialog.Header>
			<Dialog.Title>{irisT("Add Folder", $irisLocale)}</Dialog.Title>
		</Dialog.Header>

		<div class="space-y-3 py-2">
			<div>
				<label for="ds-folder-name" class="text-sm font-medium">{irisT("Folder name", $irisLocale)}</label>
				<Input id="ds-folder-name" bind:value={folderName} placeholder={irisT("New folder", $irisLocale)} class="mt-1" />
			</div>
			<p class="text-xs text-muted-foreground">
				{irisT("Will be created under folder #", $irisLocale)}{parentId ?? '—'}.
			</p>
		</div>

		<div class="flex items-center justify-end gap-2 border-t pt-3">
			<Button variant="outline" disabled={isSaving} onclick={close}>{irisT("Cancel", $irisLocale)}</Button>
			<Button disabled={isSaving} onclick={save}>
				{#if isSaving}
					<RotateCwIcon class="h-4 w-4 animate-spin" />
					{irisT("Saving...", $irisLocale)}{:else}
					<SaveIcon class="h-4 w-4" />
					{irisT("Create folder", $irisLocale)}{/if}
			</Button>
		</div>
	</Dialog.Content>
</Dialog.Root>
