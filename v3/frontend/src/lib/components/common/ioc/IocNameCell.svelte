<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import ClipboardCopy from '$lib/components/ui/clipboard-copy/clipboard-copy.svelte';

	export let href: string | undefined = undefined;
	export let id: number | undefined = undefined;
	export let value: string;
</script>

<div class="group flex min-w-0 max-w-full items-start gap-1">
	{#if href}
		<a {href} class="block min-w-0 flex-1 hover:opacity-80">
			<span class="block text-xs text-muted-foreground">{irisT('IOC #', $irisLocale)}{id}</span>
			<span
				class="line-clamp-3 whitespace-pre-wrap break-all font-mono text-xs font-semibold text-primary"
				title={value}>{value}</span
			>
		</a>
	{:else}
		<span
			class="line-clamp-3 min-w-0 flex-1 whitespace-pre-wrap break-all font-mono text-xs"
			title={value}>{value}</span
		>
	{/if}
	<ClipboardCopy
		{value}
		tooltipText="Copy IOC value"
		size={12}
		alwaysVisible
		className="mt-0.5 shrink-0"
	/>
</div>
