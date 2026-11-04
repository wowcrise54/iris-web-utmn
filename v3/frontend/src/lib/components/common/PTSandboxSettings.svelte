<script lang="ts">
	import { ApiService } from '$lib/services/api.service';
	import type { ModuleDetail } from '$lib/services/modules.service';
	import { Button } from '$lib/components/ui/button';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const locale = useLocale();
	let { module }: { module: ModuleDetail } = $props();
	let busy = $state(false);
	let result = $state<Record<string, unknown> | null>(null);
	const previous = $derived(module.module_config.find(p => p.param_name === 'sandbox_url')?.connection_check);
	const shown = $derived(result ?? previous);
	$effect(() => { module.module_config; result = null; });
	async function check() {
		busy = true;
		try {
			const res = await ApiService.post<Record<string, unknown>>(`/manage/modules/${module.id}/check-connection`, {});
			result = res.ok && res.data && typeof res.data !== 'string' ? res.data : { ok: false, error: res.error?.message ?? 'Connection check failed' };
		} finally { busy = false; }
	}
</script>

<section class="my-4 space-y-3 rounded-md border p-4">
	<h3 class="font-semibold">PT Sandbox 5.37</h3>
	<p class="text-sm text-muted-foreground">{irisT('File checks from the incident and /sandbox check in the war room. Background analysis, a separate chat result, full report and original logs, optional Yuki analysis.', $locale)}</p>
	<p class="text-sm">{irisT('Save the settings below, then check the connection. The check verifies the product version and lists VM images without uploading files.', $locale)}</p>
	<Button variant="outline" disabled={busy} onclick={check}>{busy ? irisT('Checking connection…', $locale) : irisT('Check connection', $locale)}</Button>
	{#if shown}
		<p role="status" class={shown.ok ? 'text-sm text-green-600' : 'text-sm text-destructive'}>
			{shown.ok ? irisT('Connection verified', $locale) : irisT('Connection not verified', $locale)} · {String(shown.version ?? '5.37')}
			{#if shown.checked_at} · {String(shown.checked_at)}{/if}
		</p>
		{#if shown.error}<p class="text-sm text-destructive">{String(shown.error)}</p>{/if}
		{#if shown.images}<details><summary class="cursor-pointer text-sm">{irisT('Available VM images', $locale)}</summary><pre class="max-h-56 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(shown.images, null, 2)}</pre></details>{/if}
	{:else}<p class="text-sm text-muted-foreground">{irisT('Connection has not been checked for the saved settings.', $locale)}</p>{/if}
</section>
