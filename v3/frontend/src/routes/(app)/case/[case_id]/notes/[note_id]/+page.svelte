<!--
  Note detail route page. The actual panel UI lives in NoteDetailView so the
  same content can be rendered inside a modal (NoteDetailDialog) reached from
  mention chips in the markdown editor.
-->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import NoteDetailView from './NoteDetailView.svelte';

	const irisLocale = useLocale();
	const caseId = $derived(Number(page.params.case_id));
	const noteId = $derived(Number(page.params.note_id));

	const handleAfterDelete = () => {
		goto(`/case/${caseId}/notes`);
	};
</script>

<svelte:head>
	<title>#{caseId} - {irisT("Note", $irisLocale)} #{noteId}</title>
</svelte:head>

{#if Number.isFinite(noteId)}
	<NoteDetailView {caseId} {noteId} onAfterDelete={handleAfterDelete} />
{/if}
