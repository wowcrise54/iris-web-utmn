<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { BugIcon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import { toast } from '$lib/components/ui/toast';
	import { BugReportsService } from '$lib/services/bug-reports.service';
	import { getLastRequestId } from '$lib/observability/request-id-store';
	import { isSentryInitialized } from '$lib/observability/init';

	type Props = {
		open: boolean;
		onOpenChange: (value: boolean) => void;
	};
	let { open, onOpenChange }: Props = $props();

	let title = $state('');
	let description = $state('');
	let submitting = $state(false);
	let submitError = $state<string | null>(null);

	const reset = () => {
		title = '';
		description = '';
		submitError = null;
	};

	const close = () => {
		if (submitting) return;
		reset();
		onOpenChange(false);
	};

	// Try the Sentry path first when the SDK is loaded; on any failure
	// (SDK missing, network, DSN misconfigured) fall through to the
	// backend endpoint. That way the button always has SOMEWHERE to
	// land the report even on installs that haven't set up reporting.
	const submitToSentry = async (): Promise<boolean> => {
		if (!isSentryInitialized()) return false;
		try {
			const sentry = await import('@sentry/sveltekit');
			const eventId = sentry.captureMessage('User bug report', 'info');
			// captureFeedback is the headless replacement for showReportDialog
			// as of @sentry/sveltekit v8. On collectors that don't accept it
			// (some GlitchTip builds), the SDK will 400 silently — we still
			// return true here because the synthesized event landed, and the
			// operator can pair the report against it via the eventId in
			// the toast.
			sentry.captureFeedback(
				{
					name: undefined,
					email: undefined,
					message: `${title}\n\n${description}`,
					associatedEventId: eventId ?? undefined,
					url: typeof window !== 'undefined' ? window.location.href : undefined
				},
				{
					includeReplay: false
				}
			);
			toast({
				title: irisT("Bug report sent", $irisLocale),
				description: eventId ? `Event id: ${eventId}` : 'Attached to the current session',
				variant: 'success'
			});
			return true;
		} catch (error) {
			console.error('Sentry captureFeedback failed', error);
			return false;
		}
	};

	const submitToBackend = async (): Promise<boolean> => {
		const res = await BugReportsService.submit({
			title,
			description,
			url: typeof window !== 'undefined' ? window.location.href : undefined,
			user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
			request_id: getLastRequestId() ?? undefined
		});
		if (res.ok && res.data && typeof res.data !== 'string') {
			toast({
				title: irisT("Bug report received", $irisLocale),
				description: irisT("Operators will be able to see this in the activity log.", $irisLocale),
				variant: 'success'
			});
			return true;
		}
		submitError =
			(typeof res.data === 'object' && res.data && 'message' in res.data
				? (res.data as { message?: string }).message
				: null) ??
			res.error?.message ??
			'Failed to submit bug report';
		return false;
	};

	const submit = async () => {
		if (!title.trim() || !description.trim() || submitting) return;
		submitting = true;
		submitError = null;
		try {
			const viaSentry = await submitToSentry();
			if (viaSentry) {
				reset();
				onOpenChange(false);
				return;
			}
			const viaBackend = await submitToBackend();
			if (viaBackend) {
				reset();
				onOpenChange(false);
			}
		} finally {
			submitting = false;
		}
	};
</script>

<Dialog.Root {open} onOpenChange={(v) => (v ? onOpenChange(v) : close())}>
	<Dialog.Content class="max-w-lg">
		<Dialog.Header>
			<Dialog.Title class="flex items-center gap-2">
				<BugIcon size={16} />
				{irisT("Report an issue", $irisLocale)}
			</Dialog.Title>
			<Dialog.Description>
				{irisT("Describe what you were doing when things went wrong. The report is sent to the\n\t\t\t\terror-reporting collector when enabled, or logged on the server as a fallback. Case content,\n\t\t\t\tcredentials, and IOCs are redacted from any auto-attached diagnostics.", $irisLocale)}
			</Dialog.Description>
		</Dialog.Header>

		<div class="grid gap-3 py-2">
			<div class="flex flex-col gap-1">
				<label
					for="bug-report-title"
					class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
				>
					{irisT("Title", $irisLocale)}
				</label>
				<Input
					id="bug-report-title"
					placeholder={irisT("One-line summary", $irisLocale)}
					maxlength={200}
					bind:value={title}
					disabled={submitting}
				/>
			</div>
			<div class="flex flex-col gap-1">
				<label
					for="bug-report-desc"
					class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
				>
					{irisT("What happened", $irisLocale)}
				</label>
				<Textarea
					id="bug-report-desc"
					rows={6}
					placeholder={irisT("Steps to reproduce, expected vs. actual behaviour, error message if any.", $irisLocale)}
					bind:value={description}
					disabled={submitting}
				/>
			</div>
			<p class="text-2xs text-muted-foreground">
				{irisT("Auto-attached: current URL, browser user-agent, and the last server request id (", $irisLocale)}{getLastRequestId() ??
					'none yet'}).
			</p>
			{#if submitError}
				<p class="whitespace-pre-wrap text-2xs text-destructive">{submitError}</p>
			{/if}
		</div>

		<Dialog.Footer>
			<Button variant="outline" onclick={close} disabled={submitting}>{irisT("Cancel", $irisLocale)}</Button>
			<Button onclick={submit} disabled={submitting || !title.trim() || !description.trim()}>
				{submitting ? irisT("Sending…", $irisLocale) : irisT("Send report", $irisLocale)}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
