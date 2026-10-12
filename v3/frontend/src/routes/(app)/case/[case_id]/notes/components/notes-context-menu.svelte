<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { Button } from '$lib/components/ui/button';
	import type { ContextMenu } from '../types';

	type Props = {
		contextMenu: ContextMenu;
		/** When false, mutating entries (new/rename/move/delete) are hidden.
		 *  Read-only users still get the copy-link/copy-md-link entries. */
		canEdit?: boolean;
		onNewNote: (folderId?: number) => void;
		onNewFolder: (folderId?: number) => void;
		onCopyLink: (noteId?: number) => void;
		onCopyMdLink: (noteId?: number) => void;
		onRename: () => void;
		onMove: () => void;
		onDelete: () => void;
	};

	let {
		contextMenu,
		canEdit = true,
		onNewNote,
		onNewFolder,
		onCopyLink,
		onCopyMdLink,
		onRename,
		onMove,
		onDelete
	}: Props = $props();
</script>

<div
	class="fixed z-50 min-w-[180px] rounded-md border bg-background p-1 shadow-md"
	style:left="{contextMenu.x}{irisT("px", $irisLocale)}"
	style:top="{contextMenu.y}{irisT("px", $irisLocale)}"
	tabindex="0"
	role="menu"
	onclick={(event) => event.stopPropagation()}
	onkeydown={(event) => event.stopPropagation()}
>
	{#if contextMenu.source === 'folder' && contextMenu.folderId && canEdit}
		<Button
			variant="ghost"
			class="w-full justify-start"
			onclick={() => onNewNote(contextMenu.folderId)}
		>
			{irisT("New note", $irisLocale)}
		</Button>

		<Button
			variant="ghost"
			class="w-full justify-start"
			onclick={() => onNewFolder(contextMenu.folderId)}
		>
			{irisT("New folder", $irisLocale)}
		</Button>
	{:else if contextMenu.source === 'note'}
		<Button
			variant="ghost"
			class="w-full justify-start"
			onclick={() => onCopyLink(contextMenu.noteId)}>{irisT("Copy link", $irisLocale)}</Button
		>

		<Button
			variant="ghost"
			class="w-full justify-start"
			onclick={() => onCopyMdLink(contextMenu.noteId)}
		>
			{irisT("Copy MD link", $irisLocale)}
		</Button>
	{/if}

	{#if canEdit}
		<hr class="my-1" />

		<Button variant="ghost" class="w-full justify-start" onclick={onRename}>{irisT("Rename", $irisLocale)}</Button>

		<Button variant="ghost" class="w-full justify-start" onclick={onMove}>{irisT("Move", $irisLocale)}</Button>

		<hr class="my-1" />

		<Button
			variant="ghost"
			class="w-full justify-start text-red-500 hover:text-red-600"
			onclick={onDelete}
		>
			{irisT("Delete", $irisLocale)}
		</Button>
	{/if}
</div>
