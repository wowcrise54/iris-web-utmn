<!--
  Saved-filter dropdown for the cases overview page. Mirrors the
  alerts saved-filter UX: pick a preset to apply it, hit the trash
  icon to delete it, hit Save to persist the current filter set as a
  new private / public preset.

  Two routes feed into this component:
    1. The dropdown lists every preset the user can see (their own
       private ones + everyone's public ones).
    2. The save button opens a small inline dialog that asks for a
       name + description + visibility before issuing the create
       call.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { BookmarkIcon, ChevronDownIcon, TrashIcon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		DropdownMenu,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuLabel,
		DropdownMenuSeparator,
		DropdownMenuTrigger
	} from '$lib/components/ui/dropdown-menu';
	import * as Dialog from '$lib/components/ui/dialog';
	import type { CasesSavedFilter } from '$lib/services/cases-filters.service';

	type SaveMeta = { name: string; description: string; isPrivate: boolean };

	type Props = {
		presets: CasesSavedFilter[];
		selectedId: string;
		hasActiveFilter: boolean;
		saving?: boolean;
		onSelect: (id: number) => void;
		onClear: () => void;
		onDelete: (id: number) => void;
		onSave: (meta: SaveMeta) => void;
		/**
		 * Which half to render. Loading a preset happens before you edit and
		 * saving one after, so the cases overview mounts the picker in its
		 * filter panel's header and the save button in its footer. `both`
		 * keeps them side by side for any other caller.
		 */
		part?: 'both' | 'presets' | 'save';
	};

	let {
		presets,
		selectedId,
		hasActiveFilter,
		saving = false,
		onSelect,
		onClear,
		onDelete,
		onSave,
		part = 'both'
	}: Props = $props();

	let saveOpen = $state(false);
	let saveName = $state('');
	let saveDescription = $state('');
	let savePrivate = $state(true);

	const selectedPresetName = $derived(() => {
		const id = Number(selectedId);
		if (!Number.isFinite(id)) return null;
		return presets.find((p) => p.filter_id === id)?.filter_name ?? null;
	});

	const openSave = () => {
		saveName = selectedPresetName() ?? '';
		saveDescription = '';
		savePrivate = true;
		saveOpen = true;
	};

	const submitSave = () => {
		const name = saveName.trim();
		if (!name) return;
		onSave({ name, description: saveDescription.trim(), isPrivate: savePrivate });
		saveOpen = false;
	};
</script>

<div class="flex items-center gap-2">
	{#if part !== 'save'}
		<DropdownMenu>
			<DropdownMenuTrigger>
				<Button variant="outline" size="sm" class="gap-1">
					<BookmarkIcon class="size-4" />
					<span class="max-w-[160px] truncate">
						{selectedPresetName() ?? 'Saved filters'}
					</span>
					<ChevronDownIcon class="size-3" />
				</Button>
			</DropdownMenuTrigger>

			<DropdownMenuContent align="start" class="w-72">
				<DropdownMenuLabel class="text-2xs uppercase tracking-wide text-muted-foreground">
					{irisT("Apply a preset", $irisLocale)}
				</DropdownMenuLabel>

				{#if presets.length === 0}
					<div class="px-2 py-3 text-xs text-muted-foreground">
						{irisT("No saved filters yet. Build a filter and hit", $irisLocale)} <span class="font-semibold"
							>{irisT("Save filter", $irisLocale)}</span
						> {irisT("to keep it.", $irisLocale)}
					</div>
				{:else}
					{#each presets as preset (preset.filter_id)}
						<DropdownMenuItem
							class="flex items-center justify-between gap-2 pr-1"
							onclick={() => onSelect(preset.filter_id)}
						>
							<div class="flex min-w-0 flex-1 flex-col">
								<span class="truncate text-sm">{preset.filter_name}</span>
								<span class="text-2xs text-muted-foreground">
									{preset.filter_is_private ? irisT("Private", $irisLocale) : irisT("Public", $irisLocale)}
									{#if preset.filter_description}· {preset.filter_description}{/if}
								</span>
							</div>
							<button
								type="button"
								class="rounded p-1 text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
								aria-label={`${irisT("Delete", $irisLocale)} ${preset.filter_name}`}
								onclick={(e) => {
									e.stopPropagation();
									onDelete(preset.filter_id);
								}}
							>
								<TrashIcon class="size-3.5" />
							</button>
						</DropdownMenuItem>
					{/each}
				{/if}

				<DropdownMenuSeparator />
				<DropdownMenuItem onclick={onClear} disabled={!selectedId && !hasActiveFilter}>
					{irisT("Clear filter", $irisLocale)}
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	{/if}

	{#if part !== 'presets'}
		<Button
			variant="outline"
			size="sm"
			disabled={!hasActiveFilter || saving}
			onclick={openSave}
			title={hasActiveFilter ? irisT("Save current filter", $irisLocale) : irisT("Build a filter first", $irisLocale)}
		>
			{saving ? irisT("Saving…", $irisLocale) : irisT("Save filter", $irisLocale)}
		</Button>
	{/if}
</div>

<!-- Mounted with the save button, so the `presets`-only half doesn't render
     a second copy of the dialog. -->
{#if part !== 'presets'}
	<Dialog.Root bind:open={saveOpen}>
		<Dialog.Content class="max-w-md">
			<Dialog.Header>
				<Dialog.Title>{irisT("Save filter", $irisLocale)}</Dialog.Title>
			</Dialog.Header>

			<div class="flex flex-col gap-3 py-2">
				<div class="flex flex-col gap-1">
					<Label for="saved-filter-name">{irisT("Name", $irisLocale)}</Label>
					<Input
						id="saved-filter-name"
						bind:value={saveName}
						placeholder={irisT("e.g. My open cases this month", $irisLocale)}
						autofocus
					/>
				</div>

				<div class="flex flex-col gap-1">
					<Label for="saved-filter-description">{irisT("Description (optional)", $irisLocale)}</Label>
					<Input
						id="saved-filter-description"
						bind:value={saveDescription}
						placeholder={irisT("What this filter is for", $irisLocale)}
					/>
				</div>

				<div class="flex items-center gap-2">
					<input
						id="saved-filter-private"
						type="checkbox"
						bind:checked={savePrivate}
						class="size-4 rounded border-border"
					/>
					<Label for="saved-filter-private" class="cursor-pointer text-sm font-normal">
						{irisT("Private (only visible to you)", $irisLocale)}
					</Label>
				</div>
			</div>

			<Dialog.Footer>
				<Button variant="outline" onclick={() => (saveOpen = false)}>{irisT("Cancel", $irisLocale)}</Button>
				<Button onclick={submitSave} disabled={!saveName.trim()}>{irisT("Save", $irisLocale)}</Button>
			</Dialog.Footer>
		</Dialog.Content>
	</Dialog.Root>
{/if}
