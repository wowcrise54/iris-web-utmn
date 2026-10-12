<!--
  One-shot API key reveal dialog.

  Shown after a successful key rotation. The key value is only
  surfaced here once — subsequent reads on the user endpoint redact
  it. Includes a copy-to-clipboard button.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { CopyIcon } from 'lucide-svelte';
	import { toast } from '$lib/components/ui/toast';

	type Props = {
		open: boolean;
		apiKey: string | null;
		onClose: () => void;
	};

	let { open = $bindable(), apiKey, onClose }: Props = $props();

	const copy = async () => {
		if (!apiKey) return;
		try {
			await navigator.clipboard.writeText(apiKey);
			toast({ title: irisT("API key copied", $irisLocale), variant: 'success' });
		} catch {
			toast({ title: irisT("Copy failed — select and copy manually", $irisLocale), variant: 'destructive' });
		}
	};

	const close = () => {
		open = false;
		onClose();
	};
</script>

<Dialog.Root
	bind:open
	onOpenChange={(o: boolean) => {
		if (!o) onClose();
	}}
>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>{irisT("New API key", $irisLocale)}</Dialog.Title>
			<Dialog.Description>
				{irisT("Copy this key now — it won't be shown again. Refresh API consumers before closing.", $irisLocale)}
			</Dialog.Description>
		</Dialog.Header>

		<div class="flex items-center gap-2 pt-2">
			<code class="flex-1 break-all rounded-md border bg-muted/30 p-2 font-mono text-2xs">
				{apiKey ?? ''}
			</code>
			<Button variant="outline" size="sm" class="h-7" onclick={copy} disabled={!apiKey}>
				<CopyIcon size={12} class="mr-1" />
				{irisT("Copy", $irisLocale)}
			</Button>
		</div>

		<Dialog.Footer class="pt-3">
			<Button onclick={close}>{irisT("Close", $irisLocale)}</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
