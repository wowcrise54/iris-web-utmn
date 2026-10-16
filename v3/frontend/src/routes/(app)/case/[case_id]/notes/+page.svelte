<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { getContext } from 'svelte';
	import { CoffeeIcon } from 'lucide-svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';
	import NotesNewFolderDialog from './components/notes-new-folder-dialog.svelte';
	import { CASE_NOTES_CTX, type CaseNotesContext } from '$lib/contexts/case-notes.context.svelte';

	const notes = getContext<CaseNotesContext>(CASE_NOTES_CTX);

	let showNewFolder = $state<boolean>(false);

	const newFolder = async (name: string) => {
		await notes.createFolder({ name });

		notes.loadTree();

		showNewFolder = false;
	};
</script>

<svelte:head>
	<title>#{page.params.case_id} - {irisT("Notes", $irisLocale)}</title>
</svelte:head>

<div class="flex h-full w-full flex-col items-center gap-2 bg-white pt-8 text-lg dark:bg-black/80">
	<p class="flex gap-2">{irisT("It looks pretty empty", $irisLocale)} <CoffeeIcon /></p>

	<Button variant="link" size="lg" onclick={() => (showNewFolder = true)}>
		<p class="text-lg">{irisT("Select a note on the left pane or click here to add a directory", $irisLocale)}</p>
	</Button>

	<p>{irisT("Right-click on a directory to add a note", $irisLocale)}</p>
</div>

<NotesNewFolderDialog
	bind:open={showNewFolder}
	onSubmit={(name) => newFolder(name)}
	onCancel={() => (showNewFolder = false)}
/>
