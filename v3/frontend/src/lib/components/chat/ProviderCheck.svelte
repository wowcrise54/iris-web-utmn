<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { Button } from '$lib/components/ui/button';
	import {
		ChatbotAdminService,
		type ProviderCheckBody,
		type ProviderCheckResult
	} from '$lib/services/chatbot-admin.service';
	const irisLocale = useLocale();
	let {
		body,
		disabled = false,
		onModel
	}: {
		body: ProviderCheckBody;
		disabled?: boolean;
		onModel: (model: string) => void;
	} = $props();
	let busy = $state(false);
	let result = $state<ProviderCheckResult | null>(null);
	let error = $state<string | null>(null);
	let checked = $state('');
	const signature = $derived(JSON.stringify(body));
	const current = $derived(checked === signature);

	function errorText(code: string | null): string {
		const messages: Record<string, string> = {
			http_401: 'Invalid API key.',
			http_403: 'Access denied by provider.',
			http_404: 'Model or API endpoint not found.',
			http_429: 'Provider quota or rate limit exceeded.',
			timeout: 'Provider request timed out.',
			connection_error: 'Could not connect to provider.',
			invalid_response: 'Provider returned an invalid response.'
		};
		return (
			irisT(messages[code ?? ''] ?? 'Provider request failed.', $irisLocale) +
			(code?.startsWith('http_') ? ` (HTTP ${code.slice(5)})` : '')
		);
	}

	async function check() {
		const request = { ...body };
		const started = signature;
		busy = true;
		result = null;
		error = null;
		try {
			const response = await ChatbotAdminService.checkProvider(request);
			checked = started;
			if (response.ok && response.data && typeof response.data !== 'string') {
				result = response.data;
			} else {
				error = response.error?.message ?? irisT('Provider request failed.', $irisLocale);
			}
		} catch {
			checked = started;
			error = irisT('Could not connect to provider.', $irisLocale);
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex flex-col gap-2 rounded border bg-muted/20 p-3 text-xs">
	<div>
		<Button variant="outline" size="sm" onclick={check} disabled={disabled || busy}>
			{irisT(busy ? 'Checking…' : 'Check provider', $irisLocale)}
		</Button>
	</div>
	<p class="text-muted-foreground">
		{irisT(
			'Checks the current form without saving. A short test request to the selected model may use tokens. No case data is sent.',
			$irisLocale
		)}
	</p>
	<div aria-live="polite">
		{#if current && error}
			<p class="text-destructive">{error}</p>
		{:else if current && result}
			{#if result.models_error}
				<p>{irisT('Could not load models:', $irisLocale)} {errorText(result.models_error)}</p>
			{:else}
				<p>{irisT('Model list available.', $irisLocale)} ({result.models.length})</p>
			{/if}
			{#if result.model_accessible === true}
				<p>{irisT('Selected model responded successfully:', $irisLocale)} {result.model}</p>
			{:else if result.model_accessible === false}
				<p class="text-destructive">
					{irisT('Selected model is not accessible:', $irisLocale)}
					{result.model} — {errorText(result.model_error)}
				</p>
			{:else}
				<p>{irisT('Select a model and check again to verify generation access.', $irisLocale)}</p>
			{/if}
			{#if result.models.length}
				<label class="mt-2 flex flex-col gap-1">
					<span>{irisT('Available models', $irisLocale)}</span>
					<select
						class="h-8 rounded border bg-background px-2"
						value=""
						onchange={(e) => onModel(e.currentTarget.value)}
					>
						<option value="" disabled>{irisT('Select a model', $irisLocale)}</option>
						{#each result.models as model}
							<option value={model}>{model}</option>
						{/each}
					</select>
				</label>
			{/if}
		{/if}
	</div>
</div>
