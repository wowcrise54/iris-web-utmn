<script>
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { ComputerIcon } from 'lucide-svelte';
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>#{page.params.case_id} - {irisT("Assets", $irisLocale)}</title>
</svelte:head>

<div class="flex h-full w-full flex-col items-center justify-center">
	<ComputerIcon size={72} class="text-blue-800 dark:text-blue-600" />
	<h1 class="my-4 text-center">{irisT("No asset selected", $irisLocale)}</h1>
	<p class="">{irisT("Select or add one from the side.", $irisLocale)}</p>
</div>
