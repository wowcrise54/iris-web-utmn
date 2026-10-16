<!--
  Read-only view of an object's enrichment payload.

  Enrichment is whatever a module attached to an IOC or an asset — a
  VT verdict, a MISP hit, a whois record. It has no fixed shape, so
  generic JSON remains available alongside any recognized provider view.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import * as Dialog from '$lib/components/ui/dialog';
	import Button from '$lib/components/ui/button/button.svelte';
	import ClipboardCopy from '$lib/components/ui/clipboard-copy/clipboard-copy.svelte';
	import OpenCTIEnrichment from './OpenCTIEnrichment.svelte';

	type Props = {
		open: boolean;
		/** What the enrichment belongs to, e.g. the IOC value. */
		subject?: string;
		enrichment: unknown;
		onClose?: () => void;
	};

	let { open = $bindable(), subject = '', enrichment, onClose }: Props = $props();

	// Modules write the payload; a cycle or a non-serialisable value in
	// there must not take the dialog down with it.
	const formatted = $derived.by(() => {
		if (enrichment === null || enrichment === undefined) return '';

		try {
			return JSON.stringify(enrichment, null, 2);
		} catch {
			return String(enrichment);
		}
	});
</script>

<Dialog.Root
	bind:open
	onOpenChange={(nextOpen) => {
		if (!nextOpen) {
			onClose?.();
		}
	}}
>
	<Dialog.Content class="flex max-h-[80vh] max-w-[840px] flex-col p-0">
		<Dialog.Header class="border-b px-6 py-4">
			<Dialog.Title class="flex min-w-0 items-center gap-2 text-base font-medium">
				<span>{irisT("Enrichment", $irisLocale)}</span>
				{#if subject}
					<span class="truncate font-mono text-sm text-muted-foreground" title={subject}>
						{subject}
					</span>
				{/if}
			</Dialog.Title>
		</Dialog.Header>

		<div class="flex-1 overflow-auto px-6 py-5">
			<OpenCTIEnrichment {enrichment} />
			{#if formatted}
				<pre
					class="whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 text-xs leading-relaxed">{formatted}</pre>
			{:else}
				<p class="text-sm text-muted-foreground">{irisT("No enrichment recorded for this object.", $irisLocale)}</p>
			{/if}
		</div>

		<div class="flex items-center justify-end gap-2 border-t px-6 py-4">
			{#if formatted}
				<ClipboardCopy value={formatted} tooltipText="Copy enrichment" alwaysVisible />
			{/if}

			<Button
				variant="outline"
				onclick={() => {
					open = false;

					onClose?.();
				}}>{irisT("Close", $irisLocale)}</Button
			>
		</div>
	</Dialog.Content>
</Dialog.Root>
