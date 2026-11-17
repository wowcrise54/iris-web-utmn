<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import type { CaseTimelineStatistics } from '$lib/services/case-timeline.service';
	import { formatDateTime } from '$lib/utils/time-formatter';

	let { statistics }: { statistics: CaseTimelineStatistics } = $props();
	const locale = useLocale();
	const maximumCount = $derived(Math.max(1, ...statistics.histogram.map((bucket) => bucket.count)));
	const summaries = $derived([
		{ title: irisT('Top sources', $locale), values: statistics.sources },
		{ title: irisT('Top categories', $locale), values: statistics.categories }
	]);
</script>

{#if statistics.histogram.length > 0}
	<section class="mx-auto mb-4 max-w-[1100px] rounded-lg border border-border bg-card px-4 py-3">
		<h3 class="text-sm font-semibold">{irisT('Events over time', $locale)}</h3>
		<ol class="mt-3 flex h-16 items-end gap-px border-b border-border">
			{#each statistics.histogram as bucket (bucket.start)}
				<li
					class="min-w-0 flex-1 rounded-t-sm bg-primary/70"
					style:height={bucket.count ? `max(2px, ${(bucket.count / maximumCount) * 100}%)` : '0'}
					title={`${formatDateTime(bucket.start)} · ${bucket.count}`}
				>
					<span class="sr-only">{formatDateTime(bucket.start)} · {bucket.count}</span>
				</li>
			{/each}
		</ol>
		<div class="mt-1 flex justify-between gap-2 text-xs tabular-nums text-muted-foreground">
			<span>{formatDateTime(statistics.histogram[0].start)}</span>
			{#if statistics.histogram.length > 1}
				<span>{formatDateTime(statistics.histogram[statistics.histogram.length - 1].start)}</span>
			{/if}
		</div>
		<div class="mt-3 grid gap-3 sm:grid-cols-2">
			{#each summaries as summary (summary.title)}
				{#if summary.values.length}
					<div class="min-w-0">
						<h4 class="mb-1 text-xs font-medium text-muted-foreground">{summary.title}</h4>
						<dl class="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-xs">
							{#each summary.values as item (item.value)}
								<dt class="break-words">{item.value}</dt>
								<dd class="tabular-nums">{item.count}</dd>
							{/each}
						</dl>
					</div>
				{/if}
			{/each}
		</div>
	</section>
{/if}
