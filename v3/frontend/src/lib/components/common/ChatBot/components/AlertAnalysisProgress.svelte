<script lang="ts">
	import type { ChatPanelContext } from '$lib/contexts/chat-panel.context.svelte';
	import { analysisActive } from '$lib/services/alert-analysis.service';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { Button } from '$lib/components/ui/button';
	let { chat }: { chat: ChatPanelContext } = $props();
	const locale = useLocale();
	const job = $derived(chat.state.alertAnalysis);
	const coverage = $derived(job?.result?.coverage);
	const phases = {
		queued: 'Queued',
		normalize: 'Normalizing events',
		map: 'Analyzing packets',
		reduce: 'Combining findings',
		verify: 'Verifying evidence',
		final: 'Final report',
		completed: 'Final report',
		failed: 'Failed',
		cancelled: 'Cancelled'
	};
</script>

{#if job}
	<div class="space-y-2 rounded-md border p-3 text-xs" aria-live="polite">
		<a class="font-medium underline" href={`/alerts/${job.alert_id}?analysis=${job.id}`}
			>{irisT('Alert analysis', $locale)} #{job.alert_id}</a
		>
		<p>{irisT(phases[job.stage] ?? job.stage, $locale)} · {irisT(job.status, $locale)}</p>
		<p>{irisT('Packets processed', $locale)}: {job.progress} / {job.total}</p>
		{#if job.result?.usage?.budget_method === 'utf8_bytes_fallback'}
			<p>{irisT('Conservative packets: the model tokenizer is not verified.', $locale)}</p>
		{:else if job.result?.usage?.budget_method === 'verified_tokenizer_estimate'}
			<p>{irisT('Verified tokenizer; token count remains an estimate.', $locale)}</p>
		{/if}
		{#if coverage}
			<p>
				{irisT('Events processed', $locale)}: {coverage.processed_events} / {coverage.available_events}
			</p>
			<p>
				{irisT(
					coverage.source_complete
						? 'Source complete'
						: 'Source incomplete: investigation coverage is limited',
					$locale
				)}
			</p>
			{#if !coverage.normalization_complete}<p>
					{irisT('Event normalization incomplete', $locale)}
				</p>{/if}
			{#if coverage.missing_events.length}<p>
					{irisT('Missing source events', $locale)}: {coverage.missing_events.length}
				</p>{/if}
		{/if}
		{#if job.error}<p role="alert" class="text-destructive">{irisT(job.error, $locale)}</p>{/if}
		{#if chat.state.analysisError}
			<p role="alert" class="text-destructive">{irisT(chat.state.analysisError, $locale)}</p>
			<Button
				size="sm"
				variant="outline"
				disabled={chat.state.loading}
				onclick={() => chat.loadAlertAnalysis(job.alert_id, job.id)}
				>{irisT('Refresh analysis status', $locale)}</Button
			>
		{/if}
		{#if analysisActive(job)}
			<Button
				size="sm"
				variant="outline"
				disabled={chat.state.loading}
				onclick={chat.cancelAlertAnalysis}>{irisT('Cancel after current request', $locale)}</Button
			>
		{:else if job.status === 'partial' && job.stage === 'completed'}
			<Button
				size="sm"
				variant="outline"
				disabled={!chat.canAnalyzeAlert}
				onclick={() => chat.analyzeAlert(job.alert_id)}
				>{irisT('Analyze updated alert', $locale)}</Button
			>
		{:else if ['failed', 'partial', 'cancelled'].includes(job.status)}
			<Button
				size="sm"
				variant="outline"
				disabled={!chat.canAnalyzeAlert}
				onclick={chat.retryAlertAnalysis}>{irisT('Retry analysis', $locale)}</Button
			>
		{/if}
	</div>
{/if}
