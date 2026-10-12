<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { page } from '$app/state';
	import { ExternalLinkIcon, TrafficConeIcon } from 'lucide-svelte';
</script>

<div class="flex h-full w-full flex-col items-center justify-center gap-y-2">
	<TrafficConeIcon size={72} class="text-blue-800 dark:text-blue-600" />
	<h1>{irisT("Error", $irisLocale)} {page.status}</h1>
	<h2>{page.error?.message}</h2>
	<p>{irisT("Our apologies.", $irisLocale)}</p>
	<!-- TODO: ADD LINK -->
	<a
		href="https://github.com/dfir-iris/iris-web/issues"
		class="flex flex-row items-center gap-x-1 underline"
		>{irisT("Report an issue on our GitHub", $irisLocale)} <ExternalLinkIcon size={16} /></a
	>
</div>
