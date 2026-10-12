<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import * as Dialog from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Switch } from '$lib/components/ui/switch';
	import { AlertTriangleIcon, DownloadIcon, RefreshCwIcon } from 'lucide-svelte';
	import { toast } from '$lib/stores/toast.store';
	import { CaseTransferService } from '$lib/services/case-transfer.service';

	type Props = {
		open: boolean;
		caseId: number;
		onOpenChange: (open: boolean) => void;
	};

	let { open = $bindable(), caseId, onOpenChange }: Props = $props();

	let includeBlobs = $state(true);
	let encrypt = $state(false);
	let passphrase = $state('');
	let confirmation = $state('');
	let busy = $state(false);

	// Only surfaced once the operator has typed into both fields, so the
	// warning doesn't shout at them mid-word.
	const mismatch = $derived(
		encrypt && passphrase.length > 0 && confirmation.length > 0 && passphrase !== confirmation
	);
	const ready = $derived(!encrypt || (passphrase.length > 0 && passphrase === confirmation));

	const reset = () => {
		includeBlobs = true;
		encrypt = false;
		passphrase = '';
		confirmation = '';
	};

	const close = () => {
		// Drop the passphrase from memory as soon as the dialog goes away
		// rather than leaving it in component state until the next export.
		reset();
		onOpenChange(false);
	};

	const runExport = async () => {
		if (!ready || busy) return;
		busy = true;
		try {
			const result = await CaseTransferService.exportCase(caseId, {
				include_blobs: includeBlobs,
				...(encrypt ? { passphrase } : {})
			});

			if (!result.ok) {
				toast({
					title: irisT("Export failed", $irisLocale),
					description: result.error.message,
					variant: 'destructive'
				});
				return;
			}

			CaseTransferService.saveArchive(result.value);
			toast({ title: `Exported ${result.value.filename}` });
			close();
		} catch (err) {
			toast({
				title: irisT("Export failed", $irisLocale),
				description: (err as Error).message,
				variant: 'destructive'
			});
		} finally {
			busy = false;
		}
	};
</script>

<Dialog.Root bind:open {onOpenChange}>
	<Dialog.Content class="sm:max-w-[560px]">
		<Dialog.Header>
			<Dialog.Title>{irisT("Export case", $irisLocale)}</Dialog.Title>
			<Dialog.Description>
				{irisT("Produces a single archive holding this case and everything attached to it. War rooms,\n\t\t\t\talerts, the case chat and access rules are not included — access is decided again on the\n\t\t\t\tinstance you import into.", $irisLocale)}
			</Dialog.Description>
		</Dialog.Header>

		<div class="flex flex-col gap-5 py-2">
			<div class="flex items-start justify-between gap-4">
				<div class="min-w-0">
					<Label for="export-include-blobs" class="font-medium">{irisT("Include Datastore files", $irisLocale)}</Label>
					<p class="mt-1 text-xs text-muted-foreground">
						{irisT("Ships the file contents alongside the metadata. Turn this off for a small archive — the\n\t\t\t\t\t\tDatastore entries still travel, but without their bytes.", $irisLocale)}
					</p>
				</div>
				<Switch id="export-include-blobs" bind:checked={includeBlobs} disabled={busy} />
			</div>

			<div class="flex items-start justify-between gap-4 border-t pt-4">
				<div class="min-w-0">
					<Label for="export-encrypt" class="font-medium">{irisT("Encrypt with a passphrase", $irisLocale)}</Label>
					<p class="mt-1 text-xs text-muted-foreground">
						{irisT("Seals the archive with AES-256-GCM. Whoever imports it will be asked for the same\n\t\t\t\t\t\tpassphrase.", $irisLocale)}
					</p>
				</div>
				<Switch id="export-encrypt" bind:checked={encrypt} disabled={busy} />
			</div>

			{#if encrypt}
				<div class="flex flex-col gap-3">
					<div class="flex flex-col gap-1.5">
						<Label for="export-passphrase" class="text-xs">{irisT("Passphrase", $irisLocale)}</Label>
						<Input
							id="export-passphrase"
							type="password"
							autocomplete="new-password"
							bind:value={passphrase}
							disabled={busy}
						/>
					</div>
					<div class="flex flex-col gap-1.5">
						<Label for="export-passphrase-confirm" class="text-xs">{irisT("Confirm passphrase", $irisLocale)}</Label>
						<Input
							id="export-passphrase-confirm"
							type="password"
							autocomplete="new-password"
							bind:value={confirmation}
							disabled={busy}
						/>
						{#if mismatch}
							<p class="text-xs text-destructive">{irisT("The two passphrases don't match.", $irisLocale)}</p>
						{/if}
					</div>

					<div
						class="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-500/50 dark:bg-amber-950/40 dark:text-amber-200"
					>
						<AlertTriangleIcon size={14} class="mt-0.5 shrink-0" />
						<span>
							{irisT("IRIS cannot recover this passphrase. It is never stored, on this instance or in the\n\t\t\t\t\t\t\tarchive — lose it and the export is unreadable.", $irisLocale)}
						</span>
					</div>
				</div>
			{/if}
		</div>

		<Dialog.Footer>
			<Button variant="outline" onclick={close} disabled={busy}>{irisT("Cancel", $irisLocale)}</Button>
			<Button onclick={runExport} disabled={!ready || busy}>
				{#if busy}
					<RefreshCwIcon size={14} class="mr-2 animate-spin" />
					{irisT("Building archive…", $irisLocale)}{:else}
					<DownloadIcon size={14} class="mr-2" />
					{irisT("Export", $irisLocale)}{/if}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
