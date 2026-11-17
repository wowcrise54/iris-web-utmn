<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();
	import { PencilIcon, SparklesIcon, Trash2Icon } from 'lucide-svelte';
	export let onDelete: (() => void) | undefined = undefined;

	// Per-row actions for the IOC/asset tables. Both handlers are
	// optional: a table only gets the buttons whose callback it passed,
	// which is how the case views keep the columns they had.
	export let onEdit: (() => void) | undefined = undefined;
	export let onShowEnrichment: (() => void) | undefined = undefined;
	// An object with no enrichment still gets the button, disabled —
	// "nothing was enriched" and "enrichment isn't a thing here" are
	// different answers and the analyst is asking the first question.
	export let hasEnrichment: boolean = false;
	export let editLabel: string = 'Edit';
	export let enrichmentLabel: string = 'View enrichment';
</script>

<div class="flex items-center justify-end gap-1">
	{#if onDelete}
		<button type="button" class="rounded p-1 text-muted-foreground hover:text-destructive" title={irisT('Remove IOC from alert', $irisLocale)} aria-label={irisT('Remove IOC from alert', $irisLocale)} onclick={(e) => { e.stopPropagation(); onDelete?.(); }}><Trash2Icon class="size-3.5" /></button>
	{/if}
	{#if onShowEnrichment}
		<button
			type="button"
			class="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-default disabled:opacity-30"
			title={irisT(hasEnrichment ? enrichmentLabel : 'No enrichment', $irisLocale)}
			aria-label={irisT(enrichmentLabel, $irisLocale)}
			disabled={!hasEnrichment}
			onclick={(e) => {
				e.stopPropagation();
				onShowEnrichment?.();
			}}
		>
			<SparklesIcon class="size-3.5" />
		</button>
	{/if}

	{#if onEdit}
		<button
			type="button"
			class="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
			title={irisT(editLabel, $irisLocale)}
			aria-label={irisT(editLabel, $irisLocale)}
			onclick={(e) => {
				e.stopPropagation();
				onEdit?.();
			}}
		>
			<PencilIcon class="size-3.5" />
		</button>
	{/if}
</div>
