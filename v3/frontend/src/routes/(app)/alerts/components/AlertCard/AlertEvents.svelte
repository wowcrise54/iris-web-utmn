<script lang="ts">
	import { ChevronDown, ChevronRight } from 'lucide-svelte';
	import ClipboardCopy from '$lib/components/ui/clipboard-copy/clipboard-copy.svelte';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { mediumDateTimeFormatter } from '$lib/utils/time-formatter';

	type EventRecord = Record<string, unknown>;

	let { source }: { source: Record<string, unknown> | null | undefined } = $props();
	const locale = useLocale();
	let expanded = $state<Record<string, boolean>>({});
	let selected = $state.raw<EventRecord | null>(null);
	let showJson = $state(false);

	const isRecord = (value: unknown): value is EventRecord =>
		typeof value === 'object' && value !== null && !Array.isArray(value);
	const eventId = (event: EventRecord) =>
		event.uuid ?? (isRecord(event._meta) ? event._meta.id : undefined);
	const field = (event: EventRecord | undefined, key: string) => {
		const value = event?.[key];
		return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
	};

	const events = $derived(Array.isArray(source?.events) ? source.events.filter(isRecord) : []);
	const byId = $derived(new Map(events.map((event) => [eventId(event), event])));
	const tree = $derived(Array.isArray(source?.event_tree) ? source.event_tree : []);
	const extraEvents = $derived.by(() => {
		const ids = new Set<unknown>();
		function collect(nodes: unknown[]) {
			for (const node of nodes) {
				if (!isRecord(node)) continue;
				if (typeof node.uuid === 'string') ids.add(node.uuid);
				if (Array.isArray(node.subevents)) collect(node.subevents);
			}
		}
		collect(tree);
		return events.filter((event) => !ids.has(eventId(event)));
	});
	const details = [
		{
			label: 'Event subject',
			fields: [
				'subject.account.name',
				'subject.process.name',
				'subject.process.fullpath',
				'subject.name',
				'subject'
			]
		},
		{ label: 'Action', fields: ['action'] },
		{
			label: 'Event object',
			fields: [
				'object.account.name',
				'object.process.name',
				'object.process.fullpath',
				'object.name',
				'object'
			]
		},
		{ label: 'Status', fields: ['status'] },
		{
			label: 'Source',
			fields: [
				'event_src.host',
				'event_src.hostname',
				'event_src.ip',
				'event_src.title',
				'event_src.subsys'
			]
		}
	];
</script>

{#snippet row(
	event: EventRecord | undefined,
	path: string,
	depth: number,
	children: unknown[] = [],
	uuid = ''
)}
	<div class="event-row border-b" style:--indent={Math.min(depth, 6) * 12 + 'px'}>
		<div class="flex items-center pl-[var(--indent)]">
			{#if children.length}
				<button
					type="button"
					class="rounded p-1 hover:bg-muted"
					aria-label={irisT(
						expanded[path] ? 'Collapse related events' : 'Expand related events',
						$locale
					)}
					aria-expanded={!!expanded[path]}
					onclick={() => (expanded[path] = !expanded[path])}
				>
					{#if expanded[path]}<ChevronDown size={14} />{:else}<ChevronRight size={14} />{/if}
				</button>
			{/if}
		</div>
		{#if event}
			{@const time = field(event, 'time')}
			{@const host = field(event, 'event_src.host') || field(event, 'event_src.hostname')}
			{@const description = field(event, 'text') || field(event, 'name')}
			<button
				type="button"
				class="event-cells min-w-0 text-left hover:bg-muted aria-pressed:bg-accent"
				aria-pressed={selected === event}
				aria-label={description || String(eventId(event) ?? irisT('Event details', $locale))}
				onclick={() => (selected = event)}
			>
				<span>{mediumDateTimeFormatter(time) || time || '—'}</span>
				<span class="truncate" title={host}>{host || '—'}</span>
				<span class="truncate" title={description}>{description || '—'}</span>
			</button>
		{:else}
			<div class="min-w-0 p-2 text-muted-foreground">
				{irisT('Event data unavailable', $locale)}
				<span class="break-all font-mono text-xs">{uuid}</span>
			</div>
		{/if}
	</div>
	{#if expanded[path]}
		{@render branches(children, path, depth + 1)}
	{/if}
{/snippet}

{#snippet branches(nodes: unknown[], parent: string, depth: number)}
	{#each nodes as node, index}
		{#if isRecord(node) && typeof node.uuid === 'string'}
			{@render row(
				byId.get(node.uuid),
				parent + '/' + index,
				depth,
				Array.isArray(node.subevents) ? node.subevents : [],
				node.uuid
			)}
		{/if}
	{/each}
{/snippet}

{#if events.length || tree.length}
	<div class="events min-w-0 overflow-hidden rounded-md border text-sm">
		<div class="event-layout grid min-w-0">
			<div class="min-w-0 overflow-x-auto">
				<div class="min-w-[25rem]">
					<div class="event-row border-b bg-muted/50 font-medium text-muted-foreground">
						<span></span>
						<div class="event-cells">
							<span>{irisT('Time', $locale)}</span>
							<span>{irisT('Source host', $locale)}</span>
							<span>{irisT('Description', $locale)}</span>
						</div>
					</div>
					<div class="max-h-[28rem] overflow-y-auto">
						{@render branches(tree, '', 0)}
						{#each extraEvents as event, index}
							{@render row(event, 'event-' + index, 0)}
						{/each}
					</div>
				</div>
			</div>
			<div class="event-details min-w-0 border-t p-3">
				{#if selected}
					<div class="mb-3 flex items-center gap-2">
						<button
							type="button"
							class="rounded px-2 py-1 hover:bg-muted aria-pressed:bg-accent"
							aria-pressed={!showJson}
							onclick={() => (showJson = false)}>{irisT('Details', $locale)}</button
						>
						<button
							type="button"
							class="rounded px-2 py-1 hover:bg-muted aria-pressed:bg-accent"
							aria-pressed={showJson}
							onclick={() => (showJson = true)}>JSON</button
						>
						{#if showJson}
							<ClipboardCopy value={JSON.stringify(selected, null, 2)} alwaysVisible />
						{/if}
					</div>
					{#if showJson}
						<pre
							class="max-h-[23rem] overflow-auto rounded bg-muted/50 p-2 text-xs">{JSON.stringify(
								selected,
								null,
								2
							)}</pre>
					{:else}
						<p class="mb-3 break-words">
							{field(selected, 'text') ||
								field(selected, 'name') ||
								String(eventId(selected) ?? '')}
						</p>
						<dl class="divide-y">
							{#each details as { label, fields }}
								{@const values = [
									...new Set(fields.map((key) => field(selected ?? undefined, key)).filter(Boolean))
								]}
								{#if values.length}
									<div class="grid grid-cols-[5rem_minmax(0,1fr)] gap-2 py-2">
										<dt class="text-muted-foreground">{irisT(label, $locale)}</dt>
										<dd class="break-words">{values.join(' · ')}</dd>
									</div>
								{/if}
							{/each}
						</dl>
					{/if}
				{:else}
					<p class="text-muted-foreground">
						{irisT('Select an event to view its details', $locale)}
					</p>
				{/if}
			</div>
		</div>
	</div>
{:else}
	<p class="text-sm text-muted-foreground">{irisT('No events attached to this alert', $locale)}</p>
{/if}

<style>
	.events {
		container-type: inline-size;
	}

	@container (min-width: 42rem) {
		.event-layout {
			grid-template-columns: minmax(0, 1fr) minmax(16rem, 32%);
		}

		.event-details {
			border-top-width: 0;
			border-inline-start-width: 1px;
		}
	}

	.event-row {
		display: grid;
		grid-template-columns: calc(1.5rem + var(--indent, 0px)) minmax(0, 1fr);
	}

	.event-cells {
		display: grid;
		grid-template-columns: 9rem minmax(4rem, 1fr) minmax(0, 2fr);
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem;
		font-size: 0.75rem;
	}
</style>
