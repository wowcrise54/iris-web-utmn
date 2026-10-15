<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { Collapsible } from 'bits-ui';
	import type { Alert } from '$lib/types/resources/alert';
	import type { Asset } from '$lib/types/resources/asset';
	import type { Ioc } from '$lib/types/resources/ioc';
	import { mediumDateTimeFormatter } from '$lib/utils/time-formatter';
	import Button from '$lib/components/ui/button/button.svelte';
	import ClipboardCopy from '$lib/components/ui/clipboard-copy/clipboard-copy.svelte';
	import IocDataTable from '$lib/components/common/ioc/IocDataTable.svelte';
	import AssetDataTable from '$lib/components/common/assets/AssetDataTable.svelte';
	import EnrichmentDialog from '$lib/components/common/EnrichmentDialog.svelte';
	import { AlertRelatedGraph } from '../AlertRelatedGraph';
	import { MarkDownPreview } from '$lib/components/common/MarkDown';
	import AlertIocEditDialog from '../alert-ioc-edit-dialog.svelte';
	import AlertAssetEditDialog from '../alert-asset-edit-dialog.svelte';
	import { hasChanges, saveAlertAsset, saveAlertIoc } from '../../helpers/alert-observables';
	import { getContext } from 'svelte';
	import { USER_CTX, type UserCtx } from '$lib/contexts/user-context.context.svelte';
	import { current_user } from '$lib/stores/auth.store';
	import { AlertMaterialsService } from '$lib/services/alert-materials.service';
	import AlertArtifacts from '../AlertArtifacts.svelte';
	import ConfirmationDialog from '$lib/components/ui/dialog/ConfirmationDialog.svelte';
	import { toast } from '$lib/components/ui/toast';
	const userCtx = getContext<UserCtx>(USER_CTX);
	let creatingIoc = $state(false);
	let deletingIoc = $state<Ioc | null>(null);
	let confirmDeleteIoc = $state(false);
	const addIoc = () => {
		creatingIoc = true;
		editedIoc = { ioc_id: 0, ioc_value: '', ioc_description: '', ioc_tags: '' } as Ioc;
		iocDialogOpen = true;
	};
	const removeIoc = async () => {
		if (!canManage || !deletingIoc || saving) return;
		saving = true;
		try {
			const response = await AlertMaterialsService.removeIoc(alert.alert_id, deletingIoc.ioc_id);
			if (!response.ok) throw new Error(response.error?.message ?? 'Could not remove IOC');
			alert.iocs = alert.iocs.filter(row => row.ioc_id !== deletingIoc?.ioc_id);
			deletingIoc = null;
		} catch (e) { toast({ title: irisT(e instanceof Error ? e.message : 'Could not remove IOC', $irisLocale), variant: 'destructive' }); }
		finally { saving = false; }
	};

	let {
		alert
	}: {
		alert: Alert;
	} = $props();
	const canManage = $derived($current_user?.id != null && alert.alert_owner_id === $current_user.id && userCtx?.can('alerts_write') === true);

	let showRawAlert = $state(false);

	let enrichmentOpen = $state(false);
	let enrichmentSubject = $state('');
	let enrichmentValue = $state<unknown>(null);

	// The edited row and the dialog's own open flag are kept apart so the
	// dialog is only mounted while something is being edited — one card
	// per alert is rendered in the queue, and each carries these.
	let editedIoc = $state<Ioc | null>(null);
	let iocDialogOpen = $state(false);
	let editedAsset = $state<Asset | null>(null);
	let assetDialogOpen = $state(false);
	let saving = $state(false);

	const showEnrichment = (subject: string, enrichment: unknown) => {
		enrichmentSubject = subject;
		enrichmentValue = enrichment;
		enrichmentOpen = true;
	};

	const editIoc = (ioc: Ioc) => {
		creatingIoc = false;
		editedIoc = ioc;
		iocDialogOpen = true;
	};

	const closeIocDialog = () => {
		iocDialogOpen = false;
		editedIoc = null;
	};

	const editAsset = (asset: Asset) => {
		editedAsset = asset;
		assetDialogOpen = true;
	};

	const closeAssetDialog = () => {
		assetDialogOpen = false;
		editedAsset = null;
	};

	// `saveAlertIoc` patches the row back into `alert` itself, which is
	// what the tables render — nothing to refetch, and the other views
	// on the same alert object see the edit too.
	const saveIoc = async (ioc: Ioc, changes: Parameters<typeof saveAlertIoc>[2]) => {
		if (!canManage || saving) return;
		if (creatingIoc) {
			saving = true;
			try {
				const response = await AlertMaterialsService.createIoc(alert.alert_id, changes);
				if (!response.ok || !response.data || typeof response.data === 'string') throw new Error(response.error?.message ?? 'Could not add IOC');
				alert.iocs = [...alert.iocs, response.data];
				closeIocDialog();
			} catch (e) { toast({ title: irisT(e instanceof Error ? e.message : 'Could not add IOC', $irisLocale), variant: 'destructive' }); }
			finally { saving = false; }
			return;
		}
		if (!hasChanges(changes)) {
			closeIocDialog();
			return;
		}

		saving = true;

		const updated = await saveAlertIoc(alert, ioc.ioc_id, changes);

		saving = false;

		// A failed save leaves the dialog open with the analyst's text in
		// it — the toast says what went wrong and the edit is not lost.
		if (updated) closeIocDialog();
	};

	const saveAsset = async (asset: Asset, changes: Parameters<typeof saveAlertAsset>[2]) => {
		if (!hasChanges(changes)) {
			closeAssetDialog();
			return;
		}

		saving = true;

		const updated = await saveAlertAsset(alert, asset.asset_id, changes);

		saving = false;

		if (updated) closeAssetDialog();
	};

	const contextEntries: { key: string; value: string }[] = $derived.by(() => {
		const ctx = alert.alert_context;
		if (!ctx) return [];
		return Object.keys(ctx).map((k) => ({ key: k, value: String(ctx[k]) }));
	});
</script>

<div class="flex min-w-0 flex-col gap-4 pt-2">
	<!-- General Info + Alert Note side by side -->
	<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
		<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
			<h4 class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
				{irisT("General Info", $irisLocale)}
			</h4>

			<div class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
				<div class="text-muted-foreground">{irisT("Source", $irisLocale)}</div>
				<div class="font-medium">{alert.alert_source}</div>

				<div class="text-muted-foreground">{irisT("Source Link", $irisLocale)}</div>
				<div class="flex min-w-0 items-center gap-1">
					<a
						target="_blank"
						href={alert.alert_source_link}
						class="truncate text-blue-500 hover:underline">{alert.alert_source_link}</a
					>
					<ClipboardCopy
						value={alert.alert_source_link}
						tooltipText="Copy"
						alwaysVisible={true}
						size={11}
					/>
				</div>

				<div class="text-muted-foreground">{irisT("Source Reference", $irisLocale)}</div>
				<div class="flex min-w-0 items-center gap-1">
					<span class="truncate">{alert.alert_source_ref}</span>
					<ClipboardCopy
						value={alert.alert_source_ref}
						tooltipText="Copy"
						alwaysVisible={true}
						size={11}
					/>
				</div>

				<div class="text-muted-foreground">{irisT("Source Event Time", $irisLocale)}</div>
				<div class="flex items-center gap-1">
					{mediumDateTimeFormatter(alert.alert_source_event_time)}
					<ClipboardCopy
						value={alert.alert_source_event_time}
						tooltipText="Copy"
						alwaysVisible={true}
						size={11}
					/>
				</div>

				<div class="text-muted-foreground">{irisT("IRIS Creation Time", $irisLocale)}</div>
				<div class="flex items-center gap-1">
					{mediumDateTimeFormatter(alert.alert_creation_time)}
					<ClipboardCopy
						value={alert.alert_creation_time}
						tooltipText="Copy"
						alwaysVisible={true}
						size={11}
					/>
				</div>
			</div>
		</div>

		<div class="flex flex-col gap-4">
			{#if alert.alert_note}
				<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
					<h4 class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
						{irisT("Alert Note", $irisLocale)}
					</h4>
					<!--
					  Note is rendered as sanitized markdown (same
					  Showdown+DOMPurify pipeline as case notes). Analysts
					  commonly paste triage steps with headings/lists/code
					  fences; plain text still renders as plain text.
					-->
					<div class="text-xs leading-relaxed">
						<MarkDownPreview markdown={alert.alert_note} />
					</div>
				</div>
			{/if}

			{#if contextEntries.length}
				<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
					<h4 class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
						{irisT("Context", $irisLocale)}
					</h4>
					<div class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
						{#each contextEntries as entry (entry.key)}
							<div class="text-muted-foreground">{entry.key}</div>
							<div class="break-all">{entry.value}</div>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	</div>

	<!-- Relationships -->
	<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
		<h4 class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
			{irisT("Relationships", $irisLocale)}
		</h4>
		<AlertRelatedGraph alertId={alert.alert_id} />
	</div>

	<!-- IOCs -->
		<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
			<div class="mb-3 flex items-center justify-between"><h4 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{irisT("IOCs", $irisLocale)} ({alert.iocs.length})</h4>{#if canManage}<Button size="sm" variant="outline" disabled={saving} onclick={addIoc}>{irisT('Add IOC', $irisLocale)}</Button>{/if}</div>
			<IocDataTable
				iocs={alert.iocs}
				showDescription
				showTags
				onShowEnrichment={(ioc) => showEnrichment(ioc.ioc_value, ioc.ioc_enrichment)}
				onEdit={canManage ? editIoc : undefined}
				onDelete={canManage ? (ioc) => { deletingIoc = ioc; confirmDeleteIoc = true; } : undefined}
			/>
		</div>
	<AlertArtifacts {alert} {canManage} />

	<!-- Assets -->
	{#if alert.assets.length}
		<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
			<h4 class="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
				{irisT("Assets", $irisLocale)}
			</h4>
			<AssetDataTable
				assets={alert.assets}
				showDescription
				onShowEnrichment={(asset) => showEnrichment(asset.asset_name, asset.asset_enrichment)}
				onEdit={editAsset}
			/>
		</div>
	{/if}

	<!-- Raw Alert -->
	<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
		<div class="mb-3 flex items-center justify-between gap-2">
			<h4 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{irisT("Raw Alert", $irisLocale)}</h4>
			<ClipboardCopy
				value={JSON.stringify(alert.alert_source_content, null, 2)}
				tooltipText="Copy raw alert"
				alwaysVisible
			/>
		</div>
		<Collapsible.Root bind:open={showRawAlert}>
			<Collapsible.Trigger>
				<Button variant="outline" size="sm">
					{showRawAlert ? irisT("Hide", $irisLocale) : irisT("Show", $irisLocale)} {irisT("Raw Alert", $irisLocale)}
				</Button>
			</Collapsible.Trigger>

			<Collapsible.Content
				class="w-full overflow-auto data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down"
			>
				<pre
					class="mt-3 whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 text-xs leading-relaxed">{JSON.stringify(
						alert.alert_source_content,
						null,
						2
					)}</pre>
			</Collapsible.Content>
		</Collapsible.Root>
	</div>
</div>

<EnrichmentDialog
	bind:open={enrichmentOpen}
	subject={enrichmentSubject}
	enrichment={enrichmentValue}
/>

{#if editedIoc}
	<AlertIocEditDialog
		bind:open={iocDialogOpen}
		ioc={editedIoc}
		{saving}
		creating={creatingIoc}
		onClose={closeIocDialog}
		onSave={(changes) => editedIoc && saveIoc(editedIoc, changes)}
	/>
{/if}

<ConfirmationDialog bind:open={confirmDeleteIoc} title={irisT('Remove IOC from alert', $irisLocale)} message={deletingIoc?.ioc_value ?? ''} onConfirm={removeIoc} />

{#if editedAsset}
	<AlertAssetEditDialog
		bind:open={assetDialogOpen}
		asset={editedAsset}
		{saving}
		onClose={closeAssetDialog}
		onSave={(changes) => editedAsset && saveAsset(editedAsset, changes)}
	/>
{/if}
