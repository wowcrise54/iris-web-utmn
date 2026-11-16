<script lang="ts">
	import { getContext, untrack } from 'svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';
	import { CASE_ACCESS_CTX, type CaseAccessContext } from '$lib/contexts/case-access.context.svelte';
	import { useLocale } from '$lib/i18n/context';
	import { ApiService } from '$lib/services/api.service';

	type Event = { alert_id: number; alert_title: string; event_id: string; asset: string };
	type EventList = {
		events: Event[]; execution_enabled: boolean; module_active: boolean;
		linked_alerts: number; matched_alerts: number; saved_events: number;
	};
	type Action = {
		module: string; action: string; title: string; agent: string; hostname: string;
		parameters: Record<string, string | number | boolean>; confirmation: string;
	};
	type Result = { status: 'success' | 'failure' | 'unknown'; reason: string };

	const locale = useLocale();
	const t = (ru: string, en: string) => $locale === 'ru' ? ru : en;
	const access = getContext<CaseAccessContext>(CASE_ACCESS_CTX);
	const endpoint = $derived(`/cases/${page.params.case_id}/edr`);
	let events = $state<Event[]>([]);
	let summary = $state<EventList | null>(null);
	let enabled = $state(false);
	let selection = $state('');
	let actions = $state<Action[] | null>(null);
	let actionIndex = $state('');
	const preview = $derived(actionIndex === '' ? undefined : actions?.[Number(actionIndex)]);
	let result = $state<Result | null>(null);
	let confirmed = $state(false);
	let busy = $state(true);
	let error = $state('');
	const selected = $derived(events.find(event => key(event) === selection));
	const key = (event: Event) => `${event.alert_id}/${event.event_id}`;

	async function list(url: string) {
		events = [];
		summary = null;
		enabled = false;
		selection = '';
		actions = null;
		actionIndex = '';
		result = null;
		error = '';
		confirmed = false;
		busy = true;
		try {
			const res = await ApiService.get<EventList>(url);
			if (url !== endpoint) return;
			if (res.ok && res.data && typeof res.data === 'object') {
				events = res.data.events;
				if (typeof res.data.linked_alerts === 'number') summary = res.data;
				enabled = res.data.execution_enabled;
			} else error = res.error?.message ?? t('Не удалось загрузить события', 'Could not load events');
		} finally {
			if (url === endpoint) busy = false;
		}
	}

	$effect(() => {
		const url = endpoint;
		untrack(() => void list(url));
	});

	async function discover() {
		if (!selected || busy) return;
		const url = endpoint;
		busy = true;
		error = '';
		actions = null;
		actionIndex = '';
		result = null;
		confirmed = false;
		try {
			const res = await ApiService.get<{ actions: Action[] }>(`${url}/${key(selected)}`);
			if (url !== endpoint) return;
			if (res.ok && res.data && typeof res.data === 'object') actions = res.data.actions ?? [];
			else error = res.error?.message ?? t('Не удалось получить действия EDR', 'Could not load EDR actions');
		} finally {
			if (url === endpoint) busy = false;
		}
	}

	async function execute() {
		if (!preview?.action || !confirmed || busy || !enabled || !access.canEdit()) return;
		const url = endpoint;
		const confirmation = preview.confirmation;
		busy = true;
		error = '';
		confirmed = false;
		actions = null;
		actionIndex = '';
		try {
			const res = await ApiService.post<Result>(url, { confirmed: true, confirmation });
			if (url !== endpoint) return;
			if (res.ok && res.data && typeof res.data === 'object') result = res.data;
			else error = res.error?.message ?? t('Проверьте историю кейса', 'Check case activity');
		} finally {
			if (url === endpoint) busy = false;
		}
	}
</script>

<section class="mx-auto max-w-4xl space-y-5 p-6" aria-busy={busy}>
	<h1 class="text-xl font-semibold">{t('Реагирование', 'Response')}</h1>
	{#if summary}
		<dl class="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
			<div><dt>{t('Связанные алёрты', 'Linked alerts')}</dt><dd>{summary.linked_alerts}</dd></div>
			<div><dt>{t('Алёрты из текущего MaxPatrol', 'Alerts from the current MaxPatrol source')}</dt><dd>{summary.matched_alerts}</dd></div>
			<div><dt>{t('Сохранённые события MaxPatrol', 'Saved MaxPatrol events')}</dt><dd>{summary.saved_events}</dd></div>
			<div><dt>{t('События с сопоставленным активом', 'Events with a matching asset')}</dt><dd>{events.length}</dd></div>
		</dl>
	{/if}
	{#if events.length}
		<div class="space-y-2">
			<label class="block text-sm font-medium" for="edr-event">{t('Событие MaxPatrol', 'MaxPatrol event')}</label>
			<select id="edr-event" class="w-full rounded-md border bg-background p-2 text-sm"
				bind:value={selection} disabled={busy}
				onchange={() => { actions = null; actionIndex = ''; confirmed = false; result = null; error = ''; }}>
				<option value="">{t('Выберите событие', 'Select an event')}</option>
				{#each events as event (key(event))}
					<option value={key(event)}>#{event.alert_id} · {event.alert_title} · {event.asset} · {event.event_id}</option>
				{/each}
			</select>
		</div>
		<Button disabled={!selected || busy} onclick={discover}>{t('Проверить доступные действия', 'Check available actions')}</Button>
	{:else if !busy && !error}
		<p class="text-sm text-muted-foreground">
			{#if summary && !summary.linked_alerts}
				{t('К кейсу не привязаны алёрты.', 'No alerts are linked to this case.')}
			{:else if summary && !summary.module_active}
				{t('Модуль MaxPatrol SIEM выключен.', 'The MaxPatrol SIEM module is disabled.')}
			{:else if summary && !summary.matched_alerts}
				{t('Среди привязанных алёртов нет импортированных из текущего источника MaxPatrol SIEM.', 'None of the linked alerts were imported from the current MaxPatrol SIEM source.')}
			{:else if summary && !summary.saved_events}
				{t('В алёртах MaxPatrol ещё нет сохранённых событий.', 'The MaxPatrol alerts have no saved events yet.')}
			{:else}
				{t('Для поиска агента нужны ID события и сопоставленный актив.', 'Agent discovery requires an event ID and a matching asset.')}
			{/if}
		</p>
	{/if}

	{#if actions?.length}
		<div class="space-y-2">
			<label class="block text-sm font-medium" for="edr-action">{t('Действие EDR', 'EDR action')}</label>
			<select id="edr-action" class="w-full rounded-md border bg-background p-2 text-sm"
				bind:value={actionIndex} disabled={busy} onchange={() => { confirmed = false; }}>
				<option value="">{t('Выберите действие', 'Select an action')}</option>
				{#each actions as action, index}
					<option value={String(index)}>{action.title} · {action.module}/{action.action}</option>
				{/each}
			</select>
		</div>
	{:else if actions}
		<p role="status">{t('Для этого события агент не предоставил применимых действий.', 'The agent returned no applicable actions for this event.')}</p>
	{/if}
	{#if preview}
		<div class="space-y-4 rounded-md border p-4">
			<h2 class="font-medium">{preview.title}</h2>
			<dl class="space-y-2 text-sm">
				<div><dt>{t('Узел EDR', 'EDR endpoint')}</dt><dd class="break-all font-mono">{preview.hostname} · {preview.agent}</dd></div>
				{#each Object.entries(preview.parameters) as [field, value] (field)}
					<div><dt>{field}</dt><dd class="break-all font-mono">{String(value)}</dd></div>
				{/each}
			</dl>
			{#if enabled && access.canEdit()}
				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={confirmed} />
					{t('Подтверждаю выбранное действие на указанном узле', 'I confirm the selected action on this endpoint')}
				</label>
				<Button variant="destructive" disabled={!confirmed || busy} onclick={execute}>{t('Выполнить действие', 'Execute action')}</Button>
			{:else if !enabled}
				<p class="text-sm text-muted-foreground">{t('Выполнение действий EDR отключено в настройках сервера.', 'EDR execution is disabled in server settings.')}</p>
			{/if}
		</div>
	{/if}
	{#if busy}<p role="status" class="text-sm">{t('Ожидание ответа…', 'Waiting for a response…')}</p>{/if}
	{#if error}<p role="alert" class="text-sm text-destructive">{error}</p>{/if}
	{#if result}
		<p role="status" class="break-words text-sm">
			{result.status === 'success' ? t('EDR подтвердил выполнение.', 'EDR confirmed execution.')
				: result.status === 'failure' ? t('EDR сообщил об ошибке.', 'EDR reported a failure.')
				: t('Результат выполнения неизвестен. Проверьте EDR перед повтором.', 'The outcome is unknown. Check EDR before retrying.')}
			{result.reason}
		</p>
	{/if}
</section>
