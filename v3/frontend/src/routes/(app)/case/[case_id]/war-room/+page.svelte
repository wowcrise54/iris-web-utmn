<script lang="ts">
	import { page } from '$app/state';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import type { PageData } from './$types';

	const irisLocale = useLocale();
	let { data: _data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>#{page.params.case_id} - {irisT("War Room", $irisLocale)}</title>
</svelte:head>
