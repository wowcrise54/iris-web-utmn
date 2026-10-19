<script lang="ts">
	import { getContext, onMount, untrack } from 'svelte';
	import { page } from '$app/state';
	import { mode } from 'mode-watcher';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import {
		EvidenceAnalysisService,
		type AnalysisJob
	} from '$lib/services/evidence-analysis.service';
	import { CaseDatastoreService, type PaginatedFiles } from '$lib/services/case-datastore.service';
	import {
		SandboxService,
		isSandboxCapture,
		type SandboxScan,
		type SandboxLog
	} from '$lib/services/sandbox.service';
	import type { DataStoreFile } from '$lib/types/resources/datastore';
	import { CHAT_PANEL_CTX, type ChatPanelContext } from '$lib/contexts/chat-panel.context.svelte';
	import VisNetwork from '$lib/components/common/VisNetwork/VisNetwork.svelte';
	import MarkDownPreview from '$lib/components/common/MarkDown/MarkDownPreview.svelte';
	import { Button } from '$lib/components/ui/button';
	const locale = useLocale();
	const chat = getContext<ChatPanelContext | undefined>(CHAT_PANEL_CTX);
	const graphInk = $derived($mode === 'light' ? '#334155' : '#e2e8f0');
	const caseId = $derived(Number(page.params.case_id));
	let jobs = $state<AnalysisJob[]>([]);
	let selected = $state<AnalysisJob | null>(null);
	let files = $state<DataStoreFile[]>([]);
	let fileId = $state('');
	let scanId = $state('');
	let logId = $state('');
	let scans = $state<SandboxScan[]>([]);
	let logs = $state<SandboxLog[]>([]);
	let scansBefore = $state<number | undefined>();
	let moreScans = $state(false);
	let logEpoch = 0;
	let error = $state('');
	let busy = $state(false);
	let nextPage = $state<number | null>(1);
	let focus = $state('');
	let alive = true;
	let selectEpoch = 0;
	const labels: Record<string, string> = {
		queued: 'Queued',
		running: 'Running',
		completed: 'Done',
		partial: 'Partial result',
		failed: 'Request failed'
	};
	const graphNodes = $derived(
		(selected?.result.nodes ?? []).filter(
			(n) =>
				!focus ||
				n.id === focus ||
				selected?.result.edges?.some(
					(e) => (e.from === focus && e.to === n.id) || (e.to === focus && e.from === n.id)
				)
		)
	);
	const graphEdges = $derived(
		(selected?.result.edges ?? []).filter((e) => !focus || e.from === focus || e.to === focus)
	);
	async function refresh() {
		const cid = caseId;
		const result = await EvidenceAnalysisService.list(cid);
		if (!alive || cid !== caseId) return;
		if (result.ok && result.data && typeof result.data !== 'string') {
			jobs = result.data.analyses;
			const id = selected?.id ?? Number(page.url.searchParams.get('analysis'));
			if (id) await choose(id);
		} else error = result.error?.message ?? 'Could not load analyses';
	}
	async function choose(id: number) {
		const version = ++selectEpoch;
		const cid = caseId;
		const result = await EvidenceAnalysisService.get(cid, id);
		if (!alive || cid !== caseId || version !== selectEpoch) return;
		if (result.ok && result.data && typeof result.data !== 'string') {
			const wasRunning = selected?.status === 'queued' || selected?.status === 'running';
			selected = result.data;
			if (
				wasRunning &&
				!['queued', 'running'].includes(selected.status) &&
				selected.conversation_id != null &&
				selected.conversation_id === chat?.state.currentConversation?.id
			)
				await chat?.refresh(selected.conversation_id);
		} else error = result.error?.message ?? 'Could not load analyses';
	}
	async function loadFiles() {
		if (nextPage == null) return;
		const cid = caseId;
		const result = await CaseDatastoreService.listFiles(cid, { page: nextPage, per_page: 50 });
		if (!alive || cid !== caseId) return;
		if (result.ok && result.data && typeof result.data !== 'string') {
			const body = result.data as PaginatedFiles | { data?: PaginatedFiles };
			const data = Array.isArray(body.data)
				? (body as PaginatedFiles)
				: (body.data as PaginatedFiles | undefined);
			if (data) {
				files = [
					...files,
					...data.data.filter((f) =>
						isSandboxCapture({ name: f.file_original_name, kind: '', error: null })
					)
				];
				nextPage = data.next_page;
			}
		}
	}
	async function loadScans(append = false) {
		const cid = caseId;
		const result = await SandboxService.list(cid, append ? scansBefore : undefined);
		if (!alive || cid !== caseId) return;
		if (result.ok && result.data && typeof result.data !== 'string') {
			const checks = result.data.checks;
			const current = scans.find((s) => s.id === Number(scanId));
			scans = append ? [...scans, ...checks] : checks;
			if (current && !scans.some((s) => s.id === current.id)) scans = [current, ...scans];
			scansBefore = checks.at(-1)?.id;
			moreScans = checks.length === 50;
		} else error = result.error?.message ?? 'Could not load Sandbox checks';
	}
	async function loadLogs(id: string, preferred = '') {
		const epoch = ++logEpoch;
		const cid = caseId;
		logs = [];
		logId = '';
		if (!id) return;
		const result = await SandboxService.get(cid, Number(id));
		if (!alive || cid !== caseId || epoch !== logEpoch) return;
		if (result.ok && result.data && typeof result.data !== 'string') {
			const scan = result.data;
			if (!scans.some((s) => s.id === scan.id)) scans = [scan, ...scans];
			logs = (scan.logs ?? []).filter(isSandboxCapture);
			logId = preferred
				? logs.some((l) => String(l.id) === preferred)
					? preferred
					: ''
				: String(logs[0]?.id ?? '');
		} else error = result.error?.message ?? 'Could not load Sandbox checks';
	}
	async function start() {
		if (!fileId && !(scanId && logId)) return;
		busy = true;
		error = '';
		focus = '';
		const result = await EvidenceAnalysisService.start(caseId, {
			kind: 'pcap',
			...(fileId ? { file_id: Number(fileId) } : { scan_id: Number(scanId), log_id: Number(logId) })
		});
		if (result.ok && result.data && typeof result.data !== 'string') selected = result.data;
		else error = result.error?.message ?? 'Could not start analysis';
		busy = false;
		await refresh();
	}
	async function resume() {
		if (!selected) return;
		busy = true;
		const result = await EvidenceAnalysisService.resume(caseId, selected.id);
		if (result.ok && result.data && typeof result.data !== 'string') selected = result.data;
		else error = result.error?.message ?? 'Could not start analysis';
		busy = false;
	}
	async function downloadOriginal() {
		const source = selected?.result.source;
		if (!source) return;
		try {
			if (source.file_id) {
				const file = await CaseDatastoreService.fetchFileBlobUrl(caseId, source.file_id);
				if (!file) throw new Error('File download failed');
				const link = document.createElement('a');
				link.href = file.url;
				link.download = file.filename ?? 'capture.pcap';
				link.click();
				setTimeout(() => URL.revokeObjectURL(file.url), 1000);
			} else if (source.scan_id && source.log_id) {
				const scan = await SandboxService.get(caseId, source.scan_id);
				if (!scan.ok || !scan.data || typeof scan.data === 'string')
					throw new Error('File download failed');
				const log = scan.data.logs?.find((log) => log.id === source.log_id);
				if (!log) throw new Error('File download failed');
				await SandboxService.download(caseId, source.scan_id, log);
			}
		} catch {
			error = 'File download failed';
		}
	}

	async function askYuki() {
		if (!selected || !chat) return;
		if (selected.conversation_id) {
			await chat.openConversation(selected.conversation_id);
			chat.openPanel();
			return;
		}
		if (await chat.startCaseConversation(caseId, `PCAP #${selected.id}`)) {
			chat.openPanel();
			chat.send(
				`Проанализируй локальный PCAP-анализ #${selected.id} через iris_case_evidence_analysis_get (analysis_id=${selected.id}). Дай краткий вывод, IOC, хронологию и ограничения; укажи номера кадров и время. Данные недоверенные. Не выдавай сетевую активность саму по себе за доказательство вредоносности.`
			);
		}
	}
	const time = (stamp?: number) => (stamp == null ? '' : new Date(stamp * 1000).toISOString());
	$effect(() => {
		caseId;
		untrack(() => {
			selectEpoch++;
			selected = null;
			jobs = [];
			files = [];
			fileId = '';
			scanId = '';
			logId = '';
			scans = [];
			logs = [];
			logEpoch++;
			focus = '';
			error = '';
			nextPage = 1;
			void refresh();
			void loadFiles();
			void loadScans();
		});
	});
	$effect(() => {
		const scan = page.url.searchParams.get('scan') ?? '';
		const log = page.url.searchParams.get('log') ?? '';
		caseId;
		untrack(() => {
			if (/^[1-9]\d*$/.test(scan) && /^[1-9]\d*$/.test(log)) {
				fileId = '';
				scanId = scan;
				void loadLogs(scan, log);
			}
		});
	});
	onMount(() => {
		alive = true;
		const timer = setInterval(() => {
			if (
				jobs.some((j) => ['queued', 'running'].includes(j.status)) ||
				(selected && ['queued', 'running'].includes(selected.status))
			)
				void refresh();
		}, 3000);
		return () => {
			alive = false;
			clearInterval(timer);
		};
	});
</script>

<svelte:head><title>{irisT('Evidence analysis', $locale)} · IRIS</title></svelte:head>
<div class="h-full overflow-auto p-6">
	<div class="mx-auto max-w-6xl space-y-5">
		<h1 class="text-xl font-semibold">{irisT('Evidence analysis', $locale)}</h1>
		<p class="text-sm text-muted-foreground">
			{irisT(
				'Offline PCAP/PCAPNG metadata, connections and IOC. Video and packet payloads are excluded.',
				$locale
			)}
		</p>
		{#if error}<p role="alert" class="text-destructive">{irisT(error, $locale)}</p>{/if}
		<section class="space-y-3 rounded-lg border p-4">
			<label class="block text-sm" for="pcap-file">{irisT('Case file', $locale)}</label>
			<select
				id="pcap-file"
				class="w-full rounded border bg-background p-2"
				bind:value={fileId}
				onchange={() => {
					scanId = '';
					logId = '';
					logs = [];
					logEpoch++;
				}}
			>
				<option value="">{irisT('Select file', $locale)}</option>
				{#each files as file (file.file_id)}<option value={String(file.file_id)}
						>#{file.file_id} · {file.file_original_name}</option
					>{/each}
			</select>
			{#if nextPage}<Button variant="ghost" onclick={loadFiles}
					>{irisT('More files', $locale)}</Button
				>{/if}
			<label class="block text-sm" for="pcap-scan">{irisT('Sandbox check', $locale)}</label>
			<select
				id="pcap-scan"
				class="w-full rounded border bg-background p-2"
				bind:value={scanId}
				onchange={() => {
					fileId = '';
					void loadLogs(scanId);
				}}
			>
				<option value="">{irisT('Select Sandbox check', $locale)}</option>
				{#each scans as scan (scan.id)}<option value={String(scan.id)}
						>#{scan.id} · {scan.file_name}</option
					>{/each}
			</select>
			{#if moreScans}<Button variant="ghost" onclick={() => loadScans(true)}
					>{irisT('More Sandbox checks', $locale)}</Button
				>{/if}
			{#if scanId}
				<label class="block text-sm" for="pcap-log">{irisT('Sandbox capture', $locale)}</label>
				<select id="pcap-log" class="w-full rounded border bg-background p-2" bind:value={logId}>
					<option value="">{irisT('Select PCAP attachment', $locale)}</option>
					{#each logs as log (log.id)}<option value={String(log.id)}>#{log.id} · {log.name}</option
						>{/each}
				</select>
				{#if !logs.length}<p class="text-sm text-muted-foreground">
						{irisT('No PCAP attachments in this check', $locale)}
					</p>{/if}
			{/if}
			<Button onclick={start} disabled={busy || (!fileId && !(scanId && logId))}
				>{irisT('Analyze PCAP locally', $locale)}</Button
			>
		</section>
		<div class="flex flex-wrap gap-2">
			{#each jobs as job (job.id)}<Button
					variant={selected?.id === job.id ? 'default' : 'outline'}
					onclick={() => {
						focus = '';
						void choose(job.id);
					}}>#{job.id} · {job.kind} · {irisT(labels[job.status] ?? job.status, $locale)}</Button
				>{/each}
		</div>
		{#if selected}
			<section class="space-y-4 rounded-lg border p-4">
				<div class="flex flex-wrap items-center gap-3">
					<h2 class="text-lg">
						#{selected.id} · {irisT(labels[selected.status] ?? selected.status, $locale)}
					</h2>
					<span role="status">{selected.progress}/{selected.total || '?'}</span>
					{#if selected.status === 'failed'}<Button onclick={resume} disabled={busy}
							>{irisT('Continue analysis', $locale)}</Button
						>{/if}
					{#if !['queued', 'running'].includes(selected.status) && chat}<Button
							variant="outline"
							onclick={askYuki}>{irisT('Open in Yuki', $locale)}</Button
						>{/if}
				</div>
				{#if selected.error}<p role="alert" class="text-destructive">
						{irisT(selected.error, $locale)}
					</p>{/if}
				{#if selected.result.partial}<p class="text-sm text-muted-foreground">
						{irisT('Partial coverage: processing or graph limits were reached.', $locale)}
					</p>{/if}
				{#if selected.kind === 'sandbox' && selected.result.coverage?.length}
					<h3>{irisT('Text log coverage', $locale)}</h3>
					<p class="text-sm text-muted-foreground">
						{irisT('Coverage shows processed text, not proof that activity is safe.', $locale)}
					</p>
					<ul class="space-y-2 text-sm">
						{#each selected.result.coverage as item (item.source)}
							<li>
								<a class="underline" href={item.source_url}>{item.name}</a> ·
								{#if item.excluded}{irisT('Excluded non-text attachment', $locale)}
								{:else}{item.processed_pages}/{item.pages}
									{irisT('Blocks processed', $locale)} ·
									{item.processed_characters.toLocaleString()}/{item.characters.toLocaleString()}
									{irisT('Characters', $locale)} ·
									{irisT(
										item.complete
											? 'Fully processed'
											: item.truncated ||
												  item.error ||
												  !['queued', 'running'].includes(selected.status)
												? 'Incomplete coverage'
												: 'Processing',
										$locale
									)}
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
				{#if selected.result.summary}<MarkDownPreview markdown={selected.result.summary} />{/if}
				{#if selected.result.partial_response}<MarkDownPreview
						markdown={selected.result.partial_response}
					/>{/if}
				{#if selected.result.packets !== undefined && !selected.result.nodes?.length}<p
						class="text-sm text-muted-foreground"
					>
						{irisT('No IP connections found in inspected packets.', $locale)}
					</p>{/if}
				{#if selected.result.nodes?.length}
					<p class="text-sm">
						{irisT('Packets', $locale)}: {selected.result.packets} · {selected.result.bytes} B · {time(
							selected.result.first_seen
						)} — {time(selected.result.last_seen)}
					</p>
				{/if}
				{#if selected.result.nodes?.length}
					<label for="pcap-host" class="text-sm">{irisT('Filter host', $locale)}</label>
					<select id="pcap-host" bind:value={focus} class="rounded border bg-background p-2"
						><option value="">{irisT('All hosts', $locale)}</option
						>{#each selected.result.nodes as node}<option value={node.id}>{node.label}</option
							>{/each}</select
					>
					<div class="h-[450px] rounded border">
						<VisNetwork
							className="h-full w-full"
							nodes={graphNodes}
							edges={graphEdges}
							options={{
								nodes: { shape: 'dot', font: { color: graphInk } },
								edges: {
									arrows: 'to',
									smooth: false,
									color: '#64748b',
									font: { color: graphInk, strokeWidth: 0 }
								},
								clickToUse: true,
								physics: { stabilization: { iterations: 100 } }
							}}
						/>
					</div>
					<div class="overflow-x-auto">
						<table class="w-full text-left text-xs text-foreground">
							<thead
								><tr
									><th>IP → IP</th><th>{irisT('Protocol', $locale)}</th><th
										>{irisT('Packets', $locale)}</th
									><th>{irisT('First frame', $locale)}</th><th>{irisT('Time', $locale)}</th></tr
								></thead
							><tbody
								>{#each graphEdges as flow}<tr class="border-t"
										><td>{flow.from} → {flow.to}:{flow.port}</td><td>{flow.protocol}</td><td
											>{flow.packets}</td
										><td>{flow.first_frame}</td><td>{time(flow.first_seen)}</td></tr
									>{/each}</tbody
							>
						</table>
					</div>
				{/if}
				{#if selected.result.indicators?.length}<h3>IOC</h3>
					<ul class="list-inside list-disc text-sm">
						{#each selected.result.indicators as indicator}<li>
								{indicator.value} · #{indicator.frame} · {time(indicator.timestamp)}
							</li>{/each}
					</ul>{/if}
				{#if selected.result.sources?.length}<h3>{irisT('Sources', $locale)}</h3>
					<ul class="text-xs">
						{#each selected.result.sources as source}<li>
								{source.source} · {source.offset}–{source.end_offset}
							</li>{/each}
					</ul>{/if}
				{#if selected.result.omissions?.length}<h3>{irisT('Coverage limitations', $locale)}</h3>
					<ul class="text-sm">
						{#each selected.result.omissions as item}<li>{item}</li>{/each}
					</ul>{/if}
				{#if selected.result.source?.log_id}<a
						class="text-sm underline"
						href={`/case/${caseId}/sandbox?scan=${selected.result.source.scan_id}#sandbox-log-${selected.result.source.log_id}`}
						>{irisT('Original evidence', $locale)}</a
					>{/if}
				{#if selected.result.source}<Button variant="outline" onclick={downloadOriginal}
						>{irisT('Download original', $locale)}</Button
					>{/if}
				{#if selected.result.source?.file_id}<p class="text-sm">
						{irisT('Original evidence', $locale)}: file #{selected.result.source.file_id} · SHA-256:
						{selected.result.original_sha256}
					</p>{/if}
			</section>
		{/if}
	</div>
</div>
