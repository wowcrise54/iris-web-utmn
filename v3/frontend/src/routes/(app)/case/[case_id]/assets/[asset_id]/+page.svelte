<!--
  Asset detail route page. The actual panel UI lives in AssetDetailView so the
  same content can be rendered inside a modal (AssetDetailDialog) reached from
  mention chips in the markdown editor.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { fade } from 'svelte/transition';
	import { SearchIcon } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';
	import AssetDetailView from './AssetDetailView.svelte';

	const caseId = $derived(Number(page.params.case_id));
	const assetId = $derived(Number(page.params.asset_id));

	const handleAfterDelete = () => {
		goto(`/case/${caseId}/assets`);
	};
</script>

<svelte:head>
	<title>#{caseId} - {irisT("Asset", $irisLocale)} #{assetId}</title>
</svelte:head>

{#if Number.isFinite(assetId)}
	<AssetDetailView {assetId} onAfterDelete={handleAfterDelete} />
{:else}
	<div in:fade class="flex h-full flex-col items-center justify-center text-center">
		<SearchIcon class="mb-4 h-16 w-16 text-muted-foreground/50" />

		<h2 class="mb-2 text-xl font-semibold text-muted-foreground">{irisT("Asset Not Found", $irisLocale)}</h2>

		<p class="text-muted-foreground">
			{irisT("Please select an asset from the list on the left, or try refreshing the page.", $irisLocale)}
		</p>

		<Button
			variant="outline"
			class="mt-6"
			onclick={() => goto(`/case/${caseId}/assets`, { replaceState: true })}
		>
			{irisT("Go to Assets List", $irisLocale)}
		</Button>
	</div>
{/if}
