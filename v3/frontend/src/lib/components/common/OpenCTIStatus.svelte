<script lang="ts">
	import { CircleCheck, CircleHelp, CircleMinus, TriangleAlert } from 'lucide-svelte';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { openctiStatuses, readOpenCTI } from '$lib/utils/opencti';
	const locale = useLocale();
	let { enrichment }: { enrichment: unknown } = $props();
	const result = $derived(readOpenCTI(enrichment));
	const status = $derived(result?.status ?? 'not_checked');
	const tone = $derived(
		status === 'matched'
			? 'match'
			: status === 'no_match'
				? 'empty'
				: status === 'not_checked' || status === 'unsupported'
					? 'neutral'
					: 'warning'
	);
	const Icon = $derived(
		tone === 'match'
			? CircleCheck
			: tone === 'empty'
				? CircleMinus
				: tone === 'warning'
					? TriangleAlert
					: CircleHelp
	);
</script>

<span
	class="opencti-status {tone}"
	title={result?.checkedAt ? `${irisT('Checked at', $locale)}: ${result.checkedAt}` : undefined}
>
	<Icon size={13} aria-hidden="true" />
	<span>OpenCTI · {irisT(openctiStatuses[status] ?? 'Unknown status', $locale)}</span>
	{#if result && (result.indicators.length || result.observables.length)}
		<span
			>· {irisT('Indicators', $locale)}: {result.indicators.length} · {irisT(
				'Observables',
				$locale
			)}: {result.observables.length}</span
		>
	{/if}
</span>

<style>
	.opencti-status {
		display: inline-flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.3rem;
		border: 1px solid currentColor;
		border-radius: 0.375rem;
		padding: 0.2rem 0.45rem;
		font-size: 0.6875rem;
		line-height: 1.4;
	}
	.match {
		color: #b91c1c;
		background: rgb(248 113 113 / 8%);
	}
	.empty {
		color: #047857;
		background: rgb(52 211 153 / 8%);
	}
	.warning {
		color: #92400e;
		background: rgb(251 191 36 / 8%);
	}
	:global(.dark) .match {
		color: #f87171;
	}
	:global(.dark) .empty {
		color: #34d399;
	}
	:global(.dark) .warning {
		color: #fbbf24;
	}
	.neutral {
		color: hsl(var(--muted-foreground));
	}
</style>
