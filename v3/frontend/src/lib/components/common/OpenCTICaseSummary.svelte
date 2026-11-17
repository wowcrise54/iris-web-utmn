<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { openctiStatuses, readOpenCTISummary, text } from '$lib/utils/opencti';
	const locale = useLocale();
	let { attributes }: { attributes: unknown } = $props();
	const summary = $derived(readOpenCTISummary(attributes));
</script>

{#if summary}
	<section class="m-4 space-y-2 rounded-md border p-4" aria-label={irisT('OpenCTI', $locale)}>
		<h3 class="text-sm font-semibold">OpenCTI · {irisT('Case enrichment', $locale)}</h3>
		<p class="text-xs text-muted-foreground">
			{irisT('Case and linked alert IOCs', $locale)}: {summary.total} · {summary.updatedAt}
		</p>
		<div class="flex flex-wrap gap-3 text-sm">
			{#each summary.counts as [status, count]}<span
					>{irisT(openctiStatuses[status] ?? 'Unknown status', $locale)}: {count}</span
				>{/each}
		</div>
		<details class="text-sm">
			<summary class="cursor-pointer">{irisT('IOCs', $locale)}</summary>
			<ul class="mt-2 space-y-1">
				{#each summary.iocs as ioc}
					<li class="break-all">
						<span class="font-mono">{text(ioc.value)}</span> · {irisT(
							openctiStatuses[text(ioc.status)] ?? 'Unknown status',
							$locale
						)}
					</li>
				{/each}
			</ul>
		</details>
	</section>
{/if}
