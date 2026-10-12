<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { BiohazardIcon } from 'lucide-svelte';
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>#{page.params.case_id} - IOCs</title>
</svelte:head>

<div class="flex h-full w-full flex-col items-center justify-center">
	<BiohazardIcon size={72} class="mx-auto mt-auto text-blue-800 dark:text-blue-600"></BiohazardIcon>
	<h1 class="my-4 text-center">{irisT("No IOC selected", $irisLocale)}</h1>
	<p class="mb-auto text-center">{irisT("Select or add one from the side.", $irisLocale)}</p>
</div>
