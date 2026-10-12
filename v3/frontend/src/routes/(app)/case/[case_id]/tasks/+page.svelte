<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { ClipboardListIcon } from 'lucide-svelte';
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>#{page.params.case_id} - Tasks</title>
</svelte:head>

<div class="flex h-full w-full flex-col items-center justify-center">
	<ClipboardListIcon size={72} class="mx-auto mt-auto text-blue-800 dark:text-blue-600" />
	<h1 class="my-4 text-center">{irisT("No task selected", $irisLocale)}</h1>
	<p class="mb-auto text-center">{irisT("Select or add one from the side.", $irisLocale)}</p>
</div>
