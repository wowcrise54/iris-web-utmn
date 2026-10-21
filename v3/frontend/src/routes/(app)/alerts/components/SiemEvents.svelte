<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { SiemEventsService, type SiemEventPage } from '$lib/services/siem-events.service';
	import Button from '$lib/components/ui/button/button.svelte';

	let { alertId }: { alertId: number } = $props();
	const irisLocale = useLocale();
	let open = $state(false);
	let loading = $state(false);
	let error = $state('');
	let page = $state<SiemEventPage | null>(null);
	let selected = $state<string | null>(null);
	let requestedOffset = $state(0);
	let controller: AbortController | undefined;

	$effect(() => {
		void alertId;
		open = false;
		loading = false;
		error = '';
		page = null;
		selected = null;
		requestedOffset = 0;
		return () => controller?.abort();
	});

	async function load(offset: number) {
		controller?.abort();
		const request = new AbortController();
		controller = request;
		const identifier = alertId;
		requestedOffset = offset;
		loading = true;
		error = '';
		selected = null;
		// Release the previous page before fetching the next bounded page.
		page = null;
		try {
			const response = await SiemEventsService.list(identifier, offset, { signal: request.signal });
			if (request.signal.aborted || alertId !== identifier) return;
			if (!response.ok || !response.data || typeof response.data !== 'object') {
				throw new Error('Could not load SIEM events');
			}
			page = response.data.data;
		} catch (cause) {
			if (!request.signal.aborted && alertId === identifier) {
				error = cause instanceof Error ? cause.message : 'Could not load SIEM events';
			}
		} finally {
			if (!request.signal.aborted && alertId === identifier) loading = false;
		}
	}

	function toggle() {
		open = !open;
		if (open) void load(0);
		else {
			controller?.abort();
			loading = false;
			page = null;
			selected = null;
		}
	}
</script>

<div class="my-3 rounded-lg border border-border/50 bg-muted/30 p-4">
	<Button variant="outline" size="sm" onclick={toggle} aria-expanded={open}>
		{irisT(open ? 'Hide SIEM events' : 'Show SIEM events', $irisLocale)}
	</Button>
	{#if open}
		<div class="mt-3 space-y-3" aria-busy={loading}>
			{#if loading}<p role="status">{irisT('Loading...', $irisLocale)}</p>{/if}
			{#if error}
				<p role="alert">{irisT(error, $irisLocale)}</p>
				<Button variant="outline" size="sm" onclick={() => load(requestedOffset)}
					>{irisT('Retry', $irisLocale)}</Button
				>
			{/if}
			{#if page}
				<p class="text-xs text-muted-foreground" role="status">
					{page.data.length ? page.offset + 1 : 0}–{page.offset + page.data.length} / {page.total}
				</p>
				{#each page.data as row (row.event_key)}
					<div class="rounded-md border border-border/50 p-2">
						<button
							class="w-full break-all text-left text-sm underline"
							aria-expanded={selected === row.event_key}
							onclick={() => (selected = selected === row.event_key ? null : row.event_key)}
							>{row.event_key}</button
						>
						{#if selected === row.event_key}
							{#if row.error}
								<p role="alert">{row.error} ({row.bytes} bytes)</p>
							{:else}
								<pre
									class="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(
										row.event,
										null,
										2
									)}</pre>
							{/if}
						{/if}
					</div>
				{/each}
				{#if !page.data.length}<p>{irisT('No SIEM events stored yet.', $irisLocale)}</p>{/if}
				<div class="flex gap-2">
					<Button
						variant="outline"
						size="sm"
						disabled={loading || page.offset === 0}
						onclick={() => load(0)}>{irisT('First', $irisLocale)}</Button
					>
					<Button
						variant="outline"
						size="sm"
						disabled={loading || !page.has_more || page.next_offset === null}
						onclick={() => page?.next_offset != null && load(page.next_offset)}
						>{irisT('Next', $irisLocale)}</Button
					>
				</div>
			{/if}
		</div>
	{/if}
</div>
