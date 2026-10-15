<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import {
		openctiStatuses,
		readOpenCTI,
		safeHttpUrl,
		text,
		objectText,
		markings
	} from '$lib/utils/opencti';
	const locale = useLocale();
	import OpenCTIStatus from './OpenCTIStatus.svelte';
	let { enrichment }: { enrichment: unknown } = $props();
	const result = $derived(readOpenCTI(enrichment));
</script>

{#if result}
	<section class="mb-4 space-y-3 rounded-md border p-4" aria-label={irisT('OpenCTI', $locale)}>
		<div class="flex flex-wrap items-center justify-between gap-2">
			<h3 class="font-semibold">OpenCTI</h3>
			<OpenCTIStatus {enrichment} />
		</div>
		<p class="text-xs text-muted-foreground">{irisT('Checked at', $locale)}: {result.checkedAt}</p>
		{#if result.inputValue}<p class="break-all font-mono text-xs">
				{result.inputType}: {result.inputValue}
			</p>{/if}
		{#if result.source}<a
				class="text-sm text-primary underline"
				href={result.source}
				target="_blank"
				rel="noopener noreferrer">{irisT('Open in OpenCTI', $locale)}</a
			>{/if}
		<p class="text-xs text-muted-foreground">
			{irisT('A matching observable does not confirm malicious activity.', $locale)}
		</p>
		{#each [{ label: 'Observables', items: result.observables }, { label: 'Indicators', items: result.indicators }] as group}
			<div class="space-y-2">
				<h4 class="text-sm font-medium">{irisT(group.label, $locale)} ({group.items.length})</h4>
				{#each group.items as item (item.id)}
					{@const href = safeHttpUrl(item.url)}
					<div class="rounded bg-muted/40 p-2 text-sm">
						{#if href}<a
								class="text-primary underline"
								{href}
								target="_blank"
								rel="noopener noreferrer"
								>{text(item.name) || text(item.observable_value) || item.id}</a
							>
						{:else}<span>{text(item.name) || text(item.observable_value) || item.id}</span>{/if}
						{#if item.validity}<span class="ml-2 text-xs"
								>{irisT(openctiStatuses[text(item.validity)] ?? 'Unknown status', $locale)}</span
							>{/if}
						{#if item.description || item.x_opencti_description}<p
								class="mt-1 whitespace-pre-wrap text-xs"
							>
								{text(item.description) || text(item.x_opencti_description)}
							</p>{/if}
						{#if item.pattern}<code class="mt-1 block break-all text-xs">{text(item.pattern)}</code
							>{/if}
						{#if item.valid_from || item.valid_until}<p class="text-xs text-muted-foreground">
								{text(item.valid_from)} — {text(item.valid_until)}
							</p>{/if}
						{#if objectText(item.createdBy, 'name')}<p class="text-xs">
								{irisT('Source', $locale)}: {objectText(item.createdBy, 'name')}
							</p>{/if}
						{#if markings(item.objectMarking)}<p class="text-xs">
								{markings(item.objectMarking)}
							</p>{/if}
						{#if typeof item.confidence === 'number'}<p class="text-xs">
								{irisT('Confidence', $locale)}: {item.confidence}
							</p>{/if}
					</div>
				{/each}
			</div>
		{/each}
		{#if result.relationships.length}
			<h4 class="text-sm font-medium">{irisT('Threat relationships', $locale)}</h4>
			<ul class="space-y-1 text-xs">
				{#each result.relationships as relation (relation.id)}
					<li>
						{objectText(relation.from, 'entity_type')} → {text(relation.relationship_type)} → {objectText(
							relation.to,
							'name'
						) || objectText(relation.to, 'entity_type')}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}
