<script lang="ts">
	import { getContext, onMount, untrack } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { EvidenceAnalysisService } from '$lib/services/evidence-analysis.service';
	import { useLocale } from '$lib/i18n/context';
	import { Button } from '$lib/components/ui/button';
	import { SandboxService, isSandboxCapture, type SandboxScan, type SandboxLog, type LogPage } from '$lib/services/sandbox.service';
	import { CASE_ACCESS_CTX, type CaseAccessContext } from '$lib/contexts/case-access.context.svelte';
	import { CHAT_PANEL_CTX, type ChatPanelContext } from '$lib/contexts/chat-panel.context.svelte';
	const locale = useLocale();
	const t = (ru: string, en: string) => $locale === 'ru' ? ru : en;
	const access = getContext<CaseAccessContext>(CASE_ACCESS_CTX);
	const chat = getContext<ChatPanelContext | undefined>(CHAT_PANEL_CTX);
	const caseId = $derived(Number(page.params.case_id));
	let checks = $state<SandboxScan[]>([]);
	let enabled = $state(false);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let scanId = $state('');
	let startedAt = $state('');
	let aiConsent = $state(false);
	let selected = $state<SandboxScan | null>(null);
	let logPage = $state<LogPage | null>(null);
	let currentLogId = $state<number | null>(null);
	let moreChecks = $state(true);
	const labels: Record<string, [string, string]> = {
		queued: ['В очереди', 'Queued'], uploading: ['Отправляется файл', 'Uploading'], submitting: ['Запускается проверка', 'Submitting'],
		preliminary: ['Предварительный результат', 'Preliminary result'], running: ['Анализируется', 'Running'], collecting: ['Загружаются логи', 'Collecting logs'], completed: ['Завершена', 'Completed'],
		partial: ['Получена часть логов', 'Some logs unavailable'], failed: ['Ошибка', 'Failed'],
		submission_unknown: ['Результат отправки неизвестен', 'Submission unknown'], acknowledged: ['Неопределённая отправка разобрана', 'Unknown submission acknowledged']
	};
	const statusLabel = (status: string) => labels[status] ? t(...labels[status]) : status;
	async function refresh(append = false) {
		const res = await SandboxService.list(caseId, append ? checks.at(-1)?.id : undefined);
		if (!res.ok || !res.data || typeof res.data === 'string') { error = res.error?.message ?? t('Не удалось получить проверки', 'Unable to load checks'); return; }
		enabled = res.data.enabled;
		checks = append ? [...checks, ...res.data.checks] : res.data.checks;
		moreChecks = res.data.checks.length === 50;
		if (selected) await selectCheck(selected.id);
	}
	async function load() {
		loading = true; error = ''; selected = null; logPage = null; aiConsent = false; scanId = ''; startedAt = '';
		await refresh();
		const requested = Number(page.url.searchParams.get('scan'));
		if (requested) {
			await selectCheck(requested);
			const logId = Number(page.url.searchParams.get('text_log'));
			const entry = (selected as SandboxScan | null)?.logs?.find(log => log.id === logId);
			if (entry) await read(entry, Math.max(0, Number(page.url.searchParams.get('offset')) || 0));
		}
		loading = false;
	}
	$effect(() => { caseId; untrack(() => { void load(); }); });
	onMount(() => { const timer = setInterval(() => { if (!busy) void refresh(); }, 15000); return () => clearInterval(timer); });
	async function selectCheck(id: number) {
		const res = await SandboxService.get(caseId, id);
		if (res.ok && res.data && typeof res.data !== 'string') selected = res.data;
	}
	async function submit() {
		if (!scanId.trim() || !startedAt.trim() || busy) return;
		busy = true; error = '';
		try {
			const res = await SandboxService.create(caseId, scanId.trim(), startedAt.trim());
			if (!res.ok || !res.data || typeof res.data === 'string') { error = res.error?.message ?? t('Не удалось привязать задание', 'Unable to import task'); return; }
			await selectCheck(res.data.id); await refresh();
		} finally { busy = false; }
	}
	async function read(log: SandboxLog, offset = 0) {
		error = '';
		const res = await SandboxService.text(caseId, selected!.id, log.id, offset);
		if (res.ok && res.data && typeof res.data !== 'string') { logPage = res.data; currentLogId = log.id; }
		else error = res.error?.message ?? t('Доступно скачивание оригинала', 'Download the original log');
	}
	async function analyzeCapture(log: SandboxLog) {
		if (!selected || busy || !isSandboxCapture(log)) return;
		busy = true; error = '';
		try {
			const res = await EvidenceAnalysisService.start(caseId, { kind: 'pcap', scan_id: selected.id, log_id: log.id });
			if (res.ok && res.data && typeof res.data !== 'string') await goto(`/case/${caseId}/analysis?analysis=${res.data.id}`);
			else error = res.error?.message ?? t('Не удалось запустить анализ', 'Could not start analysis');
		} finally { busy = false; }
	}
	async function download(log: SandboxLog) {
		try { await SandboxService.download(caseId, selected!.id, log); }
		catch { error = t('Не удалось скачать лог', 'Unable to download log'); }
	}
	function downloadReport() {
		if (!selected) return;
		const url = URL.createObjectURL(new Blob([JSON.stringify(selected.report, null, 2)], { type: 'application/json' }));
		const a = document.createElement('a'); a.href = url; a.download = `pt-sandbox-${selected.id}.json`; a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
	async function analyze() {
		if (!selected || !chat || !aiConsent || busy) return;
		busy = true;
		try {
			const id = await chat.startCaseConversation(caseId, `PT Sandbox #${selected.id}`);
			if (!id) { error = chat.state.error ?? 'Yuki unavailable'; return; }
			const result = await EvidenceAnalysisService.start(caseId, {kind: 'sandbox', scan_id: selected.id, conversation_id: id});
			if (result.ok && result.data && typeof result.data !== 'string') await goto(`/case/${caseId}/analysis?analysis=${result.data.id}`);
			else error = result.error?.message ?? t('Не удалось запустить анализ', 'Could not start analysis');
		} finally { busy = false; }
	}

</script>

<svelte:head><title>PT Sandbox · IRIS</title></svelte:head>
<div class="h-full overflow-auto p-6">
	<div class="mx-auto max-w-6xl space-y-5">
		<div class="flex items-center justify-between"><h1 class="text-xl font-semibold">PT Sandbox 5.39 MCP</h1><Button variant="outline" onclick={() => refresh()}>{t('Обновить', 'Refresh')}</Button><a class="text-sm underline" href={`/case/${caseId}/analysis`}>{t('Локальный анализ PCAP', 'Local PCAP analysis')}</a></div>
		{#if error}<p role="alert" class="rounded border border-destructive p-3 text-sm text-destructive">{error}</p>{/if}
		{#if !loading && !enabled}<p class="rounded border p-3 text-sm">{t('Подключите штатный MCP в Настройки → Модули → PT Sandbox.', 'Configure the built-in MCP connection in Settings → Modules → PT Sandbox.')}</p>{/if}
		{#if enabled && access.canEdit()}
			<section class="space-y-3 rounded-lg border p-4">
				<h2 class="font-medium">{t('Привязать задание PT Sandbox', 'Link a PT Sandbox task')}</h2>
				<label class="block text-sm" for="sandbox-task">Scan ID (UUID)</label>
				<input id="sandbox-task" bind:value={scanId} class="w-full rounded border bg-background p-2" />
				<label class="block text-sm" for="sandbox-start">{t('Время старта задания (UTC)', 'Task start time (UTC)')}</label>
				<input id="sandbox-start" bind:value={startedAt} placeholder="YYYY-MM-DDTHH:MM:SSZ" class="w-full rounded border bg-background p-2" />
				<Button disabled={!scanId.trim() || !startedAt.trim() || busy} onclick={submit}>{t('Получить результат', 'Import result')}</Button>
			</section>
		{/if}
		<section class="overflow-auto rounded-lg border">
			<table class="w-full text-left text-sm"><thead class="bg-muted"><tr><th class="p-3">ID</th><th>{t('Файл', 'File')}</th><th>{t('Состояние', 'Status')}</th><th>{t('Вердикт', 'Verdict')}</th><th>{t('Создана', 'Created')}</th></tr></thead>
				<tbody>{#each checks as check (check.id)}<tr class="border-t"><td class="p-3"><button class="text-primary underline" onclick={() => { logPage = null; aiConsent = false; void selectCheck(check.id); }}>#{check.id}</button></td><td class="max-w-64 break-all">{check.file_name}</td><td>{statusLabel(check.status)}</td><td>{check.verdict ?? '—'}</td><td>{new Date(check.created_at).toLocaleString()}</td></tr>{/each}</tbody>
			</table>
			{#if !checks.length}<p class="p-4 text-sm text-muted-foreground">{loading ? t('Загрузка…', 'Loading…') : t('Проверок пока нет', 'No checks yet')}</p>{/if}
			{#if moreChecks}<Button variant="ghost" onclick={() => refresh(true)}>{t('Предыдущие проверки', 'Older checks')}</Button>{/if}
		</section>
		{#if selected}
			<section class="space-y-3 rounded-lg border p-4">
				<h2 class="font-semibold">#{selected.id} · {selected.file_name}</h2>
				<p>{statusLabel(selected.status)} · {selected.verdict ?? '—'}</p>
				{#if selected.summary && !selected.remote_task}<p class="text-sm">{selected.summary.scan_state ?? ''} · {selected.summary.threat ?? ''} · {selected.summary.detections.join(', ')}</p>{/if}
				{#if selected.remote_task}
					<p class="text-sm">{t('Старт (UTC)', 'Started (UTC)')}: {selected.remote_task.start} · {t('Статус PT Sandbox', 'PT Sandbox status')}: {selected.remote_task.status} · {t('Приоритет', 'Priority')}: {selected.remote_task.priority}</p>
				{/if}
				{#if selected.sha256}<p class="break-all font-mono text-xs">SHA-256: {selected.sha256}</p>{/if}
				{#if selected.scan_id}<p class="text-xs">PT Sandbox ID: {selected.scan_id}</p>{/if}
				{#if selected.error}<p class="text-sm text-destructive">{selected.error}</p>{/if}
				{#if selected.status === 'submission_unknown' && access.canEdit()}
					<p class="text-sm">{t('Проверьте очередь PT Sandbox вручную перед новой отправкой. Задание могло быть принято.', 'Inspect the PT Sandbox queue before resubmitting: the task may have been accepted.')}</p>
					<Button variant="outline" onclick={async () => { await SandboxService.acknowledge(caseId, selected!.id); await refresh(); }}>{t('Подтверждаю: проверил очередь Sandbox', 'I have checked the Sandbox queue')}</Button>
				{/if}
				{#each selected.logs ?? [] as log (log.id)}
					<div id={`sandbox-log-${log.id}`} class="flex flex-wrap items-center gap-2 border-t pt-2 text-sm"><span class="min-w-0 flex-1 break-all">#{log.id} · {log.name} · {log.kind} · {log.size ?? '?'} B</span>
						{#if log.error}<span class="text-destructive">{log.error}</span>{:else}<Button size="sm" variant="outline" onclick={() => read(log)}>{t('Просмотр', 'View')}</Button>{#if isSandboxCapture(log)}<Button size="sm" variant="outline" disabled={busy} onclick={() => analyzeCapture(log)}>{t('PCAP · граф', 'PCAP · graph')}</Button>{/if}<Button size="sm" variant="outline" onclick={() => download(log)}>{t('Скачать оригинал', 'Download original')}</Button>{/if}
					</div>
				{/each}
				{#if selected.report}<details><summary class="cursor-pointer text-sm">{selected.remote_task ? t('JSON сводки', 'Task summary JSON') : t('Полный JSON отчёта', 'Full JSON report')}</summary><pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(selected.report, null, 2)}</pre></details>{/if}
				{#if selected.report}<Button variant="outline" onclick={downloadReport}>{t('Скачать отчёт JSON', 'Download JSON report')}</Button>{/if}
				{#if logPage}<div class="space-y-2"><p class="text-xs">{t('Смещение', 'Offset')}: {logPage.offset} {logPage.truncated ? t('· Показан ограниченный фрагмент; оригинал доступен для скачивания', '· Bounded preview; download the original for full data') : ''}</p><pre class="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">{logPage.text}</pre>
					{#if logPage.next_offset !== null}<Button variant="outline" onclick={() => read(selected!.logs!.find(log => log.id === currentLogId)!, logPage!.next_offset!)}>{t('Следующий фрагмент', 'Next page')}</Button>{/if}
				</div>{/if}
				{#if selected.report && chat}<div class="space-y-2 border-t pt-3"><label class="flex items-center gap-2 text-sm"><input type="checkbox" bind:checked={aiConsent} />{t('Разрешаю передать отчёт и текстовые логи настроенному провайдеру Yuki', 'Send this report and textual logs to the configured Yuki provider')}</label><p class="text-sm text-muted-foreground">{t('Текстовые логи обрабатываются последовательно. Большие логи могут потребовать тысячи запросов к провайдеру; действуют дневные лимиты токенов.', 'Text logs are processed sequentially. Large logs may require thousands of provider requests; daily token budgets apply.')}</p><Button disabled={!aiConsent || busy} onclick={analyze}>{t('Проанализировать с Yuki', 'Analyze with Yuki')}</Button></div>{/if}
			</section>
		{/if}
	</div>
</div>
