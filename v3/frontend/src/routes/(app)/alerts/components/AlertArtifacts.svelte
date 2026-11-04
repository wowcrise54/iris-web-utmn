<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import type { Alert } from '$lib/types/resources/alert';
	import { AlertMaterialsService, type AlertArtifact, type ArtifactBody } from '$lib/services/alert-materials.service';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Dialog from '$lib/components/ui/dialog';
	import ConfirmationDialog from '$lib/components/ui/dialog/ConfirmationDialog.svelte';
	import { toast } from '$lib/components/ui/toast';
	import { mediumDateTimeFormatter } from '$lib/utils/time-formatter';
	const irisLocale = useLocale();
	let { alert, canManage }: { alert: Alert; canManage: boolean } = $props();
	let open = $state(false);
	let busy = $state(false);
	let error = $state('');
	let edited = $state<AlertArtifact | null>(null);
	let deleting = $state<AlertArtifact | null>(null);
	let confirmDelete = $state(false);
	let file = $state<File | null>(null);
	let kind = $state('file');
	let value = $state('');
	let description = $state('');
	let includeInCase = $state(true);
	const kinds = [
		['file', 'File'], ['process', 'Process'], ['command', 'Command'],
		['path', 'File path'], ['registry', 'Registry key'], ['other', 'Other']
	];
	const begin = (row: AlertArtifact | null = null) => {
		edited = row;
		kind = row?.kind ?? 'file';
		value = row?.value ?? '';
		description = row?.description ?? '';
		includeInCase = row?.include_in_case ?? true;
		file = null;
		error = '';
		open = true;
	};
	const refresh = async () => {
		const response = await AlertMaterialsService.list(alert.alert_id);
		if (!response.ok || !Array.isArray(response.data)) throw new Error('Could not load artifacts');
		alert.artifacts = response.data;
	};
	const save = async () => {
		if (!canManage || busy) return;
		busy = true;
		error = '';
		try {
			if (kind === 'file' && !edited) {
				if (!file) return;
				await AlertMaterialsService.upload(alert.alert_id, file, description, includeInCase);
			} else {
				const body: ArtifactBody = { kind, value, description, include_in_case: includeInCase };
				const response = edited
					? await AlertMaterialsService.update(alert.alert_id, edited.id, body)
					: await AlertMaterialsService.create(alert.alert_id, body);
				if (!response.ok) throw new Error(response.error?.message ?? 'Could not save artifact');
			}
			open = false;
			await refresh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not save artifact';
			if (!open) toast({ title: irisT(error, $irisLocale), variant: 'destructive' });
		} finally { busy = false; }
	};
	const remove = async () => {
		if (!deleting || !canManage || busy) return;
		busy = true;
		try {
			const response = await AlertMaterialsService.remove(alert.alert_id, deleting.id);
			if (!response.ok) throw new Error(response.error?.message ?? 'Could not delete artifact');
			alert.artifacts = (alert.artifacts ?? []).filter(row => row.id !== deleting?.id);
			deleting = null;
		} catch (e) {
			toast({ title: irisT(e instanceof Error ? e.message : 'Could not delete artifact', $irisLocale), variant: 'destructive' });
		} finally { busy = false; }
	};
	const download = async (row: AlertArtifact) => {
		try { await AlertMaterialsService.download(alert.alert_id, row); }
		catch { toast({ title: irisT('File download failed', $irisLocale), variant: 'destructive' }); }
	};
</script>

<div class="rounded-lg border border-border/50 bg-muted/30 p-4">
	<div class="mb-3 flex items-center justify-between gap-3">
		<h4 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{irisT('Artifacts', $irisLocale)} ({alert.artifacts?.length ?? 0})</h4>
		{#if canManage}<Button size="sm" variant="outline" onclick={() => begin()}>{irisT('Add artifact', $irisLocale)}</Button>{/if}
	</div>
	{#if !alert.artifacts?.length}<p class="text-xs text-muted-foreground">{irisT('No artifacts yet.', $irisLocale)}</p>{/if}
	<div class="space-y-3">
		{#each alert.artifacts ?? [] as row (row.id)}
			<div class="rounded-md border border-border/50 p-3 text-xs">
				<div class="flex items-start justify-between gap-3">
					<div class="min-w-0 flex-1">
						<div class="mb-1 text-muted-foreground">{irisT(kinds.find(([key]) => key === row.kind)?.[1] ?? row.kind, $irisLocale)}</div>
						<pre class="whitespace-pre-wrap break-all font-mono">{row.value}</pre>
					</div>
					<div class="flex shrink-0 gap-1">
						{#if row.kind === 'file'}<Button size="sm" variant="outline" onclick={() => download(row)}>{irisT('Download', $irisLocale)}</Button>{/if}
						{#if canManage}
							<Button size="sm" variant="outline" disabled={busy} onclick={() => begin(row)}>{irisT('Edit', $irisLocale)}</Button>
							<Button size="sm" variant="outline" disabled={busy} onclick={() => { deleting = row; confirmDelete = true; }}>{irisT('Delete', $irisLocale)}</Button>
						{/if}
					</div>
				</div>
				{#if row.description}<p class="mt-2 whitespace-pre-wrap break-all">{row.description}</p>{/if}
				<div class="mt-2 text-muted-foreground">{row.created_by_name ?? row.created_by_id} · {mediumDateTimeFormatter(row.created_at)}{row.size_bytes != null ? ` · ${row.size_bytes.toLocaleString()} B` : ''}</div>
				{#if row.sha256}<div class="mt-1 break-all font-mono text-muted-foreground">SHA-256: {row.sha256}</div>{/if}
				{#if row.include_in_case}<div class="mt-1 text-muted-foreground">{irisT('Copy to case on escalation', $irisLocale)}</div>{/if}
			</div>
		{/each}
	</div>
</div>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-xl">
		<Dialog.Header><Dialog.Title>{irisT(edited ? 'Edit artifact' : 'Add artifact', $irisLocale)}</Dialog.Title><Dialog.Description>{irisT('Files and observations collected during alert analysis.', $irisLocale)}</Dialog.Description></Dialog.Header>
		<form class="space-y-4" onsubmit={(e) => { e.preventDefault(); void save(); }}>
			<label class="block text-sm">{irisT('Type', $irisLocale)}
				<select class="mt-1 w-full rounded-md border bg-background p-2" bind:value={kind} disabled={busy || edited !== null}>
					{#each kinds as [key, label]}<option value={key}>{irisT(label, $irisLocale)}</option>{/each}
				</select>
			</label>
			{#if kind === 'file' && !edited}
				<label class="block text-sm">{irisT('File', $irisLocale)} (≤ 200 MiB)
					<input type="file" class="mt-1 block w-full text-sm" disabled={busy} required onchange={(e) => file = e.currentTarget.files?.[0] ?? null} />
				</label>
			{:else}
				<label class="block text-sm">{irisT('Value', $irisLocale)}<textarea class="mt-1 min-h-24 w-full rounded-md border bg-background p-2 font-mono" bind:value maxlength={65536} required disabled={busy || kind === 'file'}></textarea></label>
			{/if}
			<label class="block text-sm">{irisT('Description', $irisLocale)}<textarea class="mt-1 min-h-20 w-full rounded-md border bg-background p-2" bind:value={description} maxlength={65536} disabled={busy}></textarea></label>
			<label class="flex items-center gap-2 text-sm"><input type="checkbox" bind:checked={includeInCase} disabled={busy} />{irisT('Copy to case on escalation', $irisLocale)}</label>
			{#if error}<p role="alert" class="text-sm text-destructive">{irisT(error, $irisLocale)}</p>{/if}
			<Dialog.Footer><Button type="button" variant="outline" disabled={busy} onclick={() => open = false}>{irisT('Cancel', $irisLocale)}</Button><Button type="submit" disabled={busy || !canManage || (kind === 'file' && !edited ? !file || file.size > 200 * 1024 * 1024 : !value.trim())}>{irisT('Save', $irisLocale)}</Button></Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>

<ConfirmationDialog bind:open={confirmDelete} title={irisT('Delete artifact', $irisLocale)} message={deleting?.value ?? ''} onConfirm={remove} />
