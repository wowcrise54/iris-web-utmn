<!--
	Mail-ingest rules + recent ingest-log viewer.

	Rules drive what an incoming email becomes (alert / case / drop).
	They're evaluated in `priority ASC` order, first match wins. The
	admin creates a rule via the "New rule" button which opens a
	dialog; existing rules edit inline with a small "Edit" affordance.

	The Poll now button triggers `POST /manage/mail/poll-now` — mostly
	a diagnostic for tuning rules against a known-good inbox.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { formatDateTime } from '$lib/utils/time-formatter';
	import { onMount } from 'svelte';
	import { InboxIcon, MailIcon, PlusIcon, RefreshCwIcon, Trash2Icon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Switch } from '$lib/components/ui/switch';
	import { toast } from '$lib/components/ui/toast';
	import * as Dialog from '$lib/components/ui/dialog';
	import ApiError from '$lib/components/ui/api-error.svelte';
	import {
		MailService,
		type MailRule,
		type MailRuleAction,
		type MailRuleBody,
		type MailIngestLogEntry
	} from '$lib/services/mail.service';

	let rules = $state<MailRule[]>([]);
	let logRows = $state<MailIngestLogEntry[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Edit dialog state. `editing` null → dialog closed; otherwise the
	// rule (or a fresh blank shape) being edited.
	let editing = $state<(MailRuleBody & { id?: number }) | null>(null);
	let saving = $state(false);
	let editError = $state<string | null>(null);

	// "Poll now" button state.
	let polling = $state(false);
	let pollResult = $state<string | null>(null);

	const ACTIONS: { value: MailRuleAction; label: string }[] = [
		{ value: 'create_alert', label: irisT("Create alert", $irisLocale) },
		{ value: 'create_case', label: irisT("Create case", $irisLocale) },
		{ value: 'drop', label: irisT("Drop (ignore)", $irisLocale) }
	];

	async function loadRules() {
		const res = await MailService.listRules();
		if (res.ok && res.data && typeof res.data !== 'string') {
			rules = (res.data as { data: MailRule[] }).data;
		}
	}

	async function loadLog() {
		const res = await MailService.listIngestLog(50);
		if (res.ok && res.data && typeof res.data !== 'string') {
			logRows = (res.data as { data: MailIngestLogEntry[] }).data;
		}
	}

	async function loadAll() {
		loading = true;
		error = null;
		try {
			await Promise.all([loadRules(), loadLog()]);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	onMount(loadAll);

	function openNew() {
		editing = {
			name: '',
			priority: 100,
			enabled: true,
			action: 'create_alert',
			match_subject_regex: null,
			match_from_regex: null,
			match_to_regex: null,
			customer_id: null,
			case_template_id: null,
			severity_id: null,
			assignee_user_id: null
		};
		editError = null;
	}

	function openEdit(rule: MailRule) {
		editing = { ...rule };
		editError = null;
	}

	async function submitEdit() {
		if (!editing) return;
		if (!editing.name || !editing.name.trim()) {
			editError = 'Name is required';
			return;
		}
		saving = true;
		editError = null;
		try {
			const body: MailRuleBody = {
				name: editing.name,
				priority: editing.priority ?? 100,
				enabled: editing.enabled ?? true,
				action: editing.action ?? 'create_alert',
				match_subject_regex: editing.match_subject_regex || null,
				match_from_regex: editing.match_from_regex || null,
				match_to_regex: editing.match_to_regex || null,
				customer_id: editing.customer_id ?? null,
				case_template_id: editing.case_template_id ?? null,
				severity_id: editing.severity_id ?? null,
				assignee_user_id: editing.assignee_user_id ?? null
			};
			const res = editing.id
				? await MailService.updateRule(editing.id, body)
				: await MailService.createRule(body);
			if (res.ok && res.data && typeof res.data !== 'string') {
				toast({ title: editing.id ? 'Rule updated' : 'Rule created', variant: 'success' });
				editing = null;
				await loadRules();
			} else {
				const data = res.data as { message?: string } | null;
				editError = data?.message ?? res.error?.message ?? 'Save failed';
			}
		} finally {
			saving = false;
		}
	}

	async function remove(rule: MailRule) {
		if (!confirm(`Delete rule "${rule.name}"?`)) return;
		const res = await MailService.deleteRule(rule.id);
		if (res.ok) {
			toast({ title: irisT("Rule deleted", $irisLocale), variant: 'success' });
			await loadRules();
		} else {
			toast({
				title: res.error?.message ?? 'Delete failed',
				variant: 'destructive'
			});
		}
	}

	async function pollNow() {
		polling = true;
		pollResult = null;
		try {
			const res = await MailService.pollNow();
			if (res.ok && res.data && typeof res.data !== 'string') {
				const payload = res.data as { skipped?: boolean; processed?: number; reason?: string };
				pollResult = payload.skipped
					? `Skipped: ${payload.reason ?? 'IMAP disabled'}`
					: `Processed ${payload.processed ?? 0} message(s).`;
				await loadLog();
			} else {
				pollResult = res.error?.message ?? 'Poll failed';
			}
		} finally {
			polling = false;
		}
	}
</script>

<div class="flex h-full w-full flex-col overflow-hidden">
	<header class="flex items-center justify-between gap-3 border-b px-5 py-3">
		<div class="flex items-center gap-2.5">
			<MailIcon size={18} class="text-muted-foreground" />
			<div class="leading-tight">
				<h1 class="text-sm font-semibold text-foreground">{irisT("Mail rules", $irisLocale)}</h1>
				<p class="text-xs text-muted-foreground">
					{irisT("Ordered rules that turn incoming email into alerts or cases. Configure the IMAP mailbox on\n\t\t\t\t\tthe", $irisLocale)}
					<a class="underline hover:text-foreground" href="/settings/server">{irisT("Server Settings", $irisLocale)}</a> {irisT("page.", $irisLocale)}
				</p>
			</div>
		</div>
		<div class="flex items-center gap-2">
			<Button size="sm" class="h-7" variant="outline" onclick={pollNow} disabled={polling}>
				<RefreshCwIcon size={12} class="mr-1" />
				{polling ? irisT("Polling…", $irisLocale) : irisT("Poll now", $irisLocale)}
			</Button>
			<Button size="sm" class="h-7" onclick={openNew}>
				<PlusIcon size={12} class="mr-1" />
				{irisT("New rule", $irisLocale)}
			</Button>
		</div>
	</header>

	<div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
		{#if error}
			<ApiError {error} showRetryButton={false} />
		{/if}

		{#if pollResult}
			<p class="rounded border bg-muted/40 p-2 text-2xs text-muted-foreground">
				{pollResult}
			</p>
		{/if}

		<section class="rounded-md border">
			<header class="flex items-center gap-2 border-b bg-muted/30 px-3 py-2">
				<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{irisT("Rules", $irisLocale)}</h2>
				<span class="text-2xs text-muted-foreground">
					({rules.length} {irisT("configured)", $irisLocale)}
				</span>
			</header>
			<div class="overflow-x-auto">
				{#if loading}
					<div class="p-6 text-center text-sm text-muted-foreground">{irisT("Loading…", $irisLocale)}</div>
				{:else if rules.length === 0}
					<div class="p-6 text-center text-sm text-muted-foreground">
						{irisT("No rules configured. The default fallback is to create an alert against the first\n\t\t\t\t\t\tcustomer with the lowest severity.", $irisLocale)}
					</div>
				{:else}
					<table class="w-full text-xs">
						<thead>
							<tr
								class="border-b bg-muted/20 text-2xs uppercase tracking-wide text-muted-foreground"
							>
								<th class="w-16 px-3 py-2 text-left">{irisT("Priority", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("Name", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("Action", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("Subject match", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("From match", $irisLocale)}</th>
								<th class="w-20 px-3 py-2 text-left">{irisT("Enabled", $irisLocale)}</th>
								<th class="w-24 px-3 py-2"></th>
							</tr>
						</thead>
						<tbody>
							{#each rules as rule (rule.id)}
								<tr class="border-b last:border-b-0 hover:bg-muted/20">
									<td class="px-3 py-2">{rule.priority}</td>
									<td class="px-3 py-2">
										<button
											class="text-left underline-offset-2 hover:underline"
											onclick={() => openEdit(rule)}
										>
											{rule.name}
										</button>
									</td>
									<td class="px-3 py-2">
										<span class="rounded bg-muted/60 px-1.5 py-0.5 text-2xs">
											{rule.action}
										</span>
									</td>
									<td
										class="max-w-[16ch] truncate px-3 py-2 font-mono text-2xs"
										title={rule.match_subject_regex ?? ''}
									>
										{rule.match_subject_regex ?? '—'}
									</td>
									<td
										class="max-w-[16ch] truncate px-3 py-2 font-mono text-2xs"
										title={rule.match_from_regex ?? ''}
									>
										{rule.match_from_regex ?? '—'}
									</td>
									<td class="px-3 py-2">
										{#if rule.enabled}
											<span
												class="rounded bg-emerald-500/15 px-1.5 py-0.5 text-2xs text-emerald-700"
												>{irisT("yes", $irisLocale)}</span
											>
										{:else}
											<span class="rounded bg-muted px-1.5 py-0.5 text-2xs text-muted-foreground"
												>{irisT("no", $irisLocale)}</span
											>
										{/if}
									</td>
									<td class="px-3 py-2 text-right">
										<button
											onclick={() => remove(rule)}
											class="rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
											title={irisT("Delete rule", $irisLocale)}
										>
											<Trash2Icon size={12} />
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		</section>

		<section class="rounded-md border">
			<header class="flex items-center gap-2 border-b bg-muted/30 px-3 py-2">
				<InboxIcon size={14} class="text-muted-foreground" />
				<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
					{irisT("Recent ingest activity", $irisLocale)}
				</h2>
			</header>
			<div class="overflow-x-auto">
				{#if logRows.length === 0}
					<div class="p-6 text-center text-2xs text-muted-foreground">
						{irisT("No messages ingested yet.", $irisLocale)}
					</div>
				{:else}
					<table class="w-full text-xs">
						<thead>
							<tr
								class="border-b bg-muted/20 text-2xs uppercase tracking-wide text-muted-foreground"
							>
								<th class="px-3 py-2 text-left">{irisT("When", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("Outcome", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("From", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("Subject", $irisLocale)}</th>
								<th class="px-3 py-2 text-left">{irisT("Object", $irisLocale)}</th>
							</tr>
						</thead>
						<tbody>
							{#each logRows as row (row.message_id)}
								<tr class="border-b last:border-b-0">
									<td class="px-3 py-2 text-2xs text-muted-foreground">
										{row.received_at ? formatDateTime(row.received_at) : '—'}
									</td>
									<td class="px-3 py-2">
										<span class="rounded bg-muted/60 px-1.5 py-0.5 text-2xs">
											{row.outcome}
										</span>
									</td>
									<td class="max-w-[20ch] truncate px-3 py-2" title={row.from_addr ?? ''}>
										{row.from_addr ?? '—'}
									</td>
									<td class="max-w-[28ch] truncate px-3 py-2" title={row.subject ?? ''}>
										{row.subject ?? '—'}
									</td>
									<td class="px-3 py-2 text-2xs text-muted-foreground">
										{#if row.outcome === 'alert_created' && row.outcome_object_id}
											<a
												class="underline hover:text-foreground"
												href={`/alerts?id=${row.outcome_object_id}`}
											>
												{irisT("alert #", $irisLocale)}{row.outcome_object_id}
											</a>
										{:else if row.outcome === 'case_created' && row.outcome_object_id}
											<a
												class="underline hover:text-foreground"
												href={`/case/${row.outcome_object_id}`}
											>
												{irisT("case #", $irisLocale)}{row.outcome_object_id}
											</a>
										{:else if row.error}
											<span class="text-destructive" title={row.error}>
												{row.error.slice(0, 40)}{row.error.length > 40 ? '…' : ''}
											</span>
										{:else}
											—
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</div>
		</section>
	</div>
</div>

<!--
  Rule editor dialog. Same shape drives create + edit — `editing.id`
  set means we're editing, absent means new. The regex fields are
  free-form; we let the backend validate on save.
-->
<Dialog.Root
	open={editing != null}
	onOpenChange={(v) => {
		if (!v) editing = null;
	}}
>
	<Dialog.Content class="max-w-lg">
		<Dialog.Header>
			<Dialog.Title>
				{editing?.id ? irisT("Edit rule", $irisLocale) : irisT("New rule", $irisLocale)}
			</Dialog.Title>
			<Dialog.Description>
				{irisT("Rules are evaluated in priority order (lowest first). First matching enabled rule wins.", $irisLocale)}
			</Dialog.Description>
		</Dialog.Header>

		{#if editing}
			<div class="space-y-3 py-2 text-xs">
				<div class="flex flex-col gap-1">
					<Label for="rule-name">{irisT("Name", $irisLocale)}</Label>
					<Input
						id="rule-name"
						class="h-7 text-xs"
						value={editing.name ?? ''}
						oninput={(e) => (editing!.name = (e.currentTarget as HTMLInputElement).value)}
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div class="flex flex-col gap-1">
						<Label for="rule-priority">{irisT("Priority", $irisLocale)}</Label>
						<Input
							id="rule-priority"
							class="h-7 text-xs"
							type="number"
							value={String(editing.priority ?? 100)}
							oninput={(e) =>
								(editing!.priority = Number((e.currentTarget as HTMLInputElement).value))}
						/>
					</div>
					<div class="flex flex-col gap-1">
						<Label for="rule-action">{irisT("Action", $irisLocale)}</Label>
						<select
							id="rule-action"
							class="h-7 rounded-md border bg-background px-2 text-xs"
							value={editing.action ?? 'create_alert'}
							onchange={(e) =>
								(editing!.action = (e.currentTarget as HTMLSelectElement).value as MailRuleAction)}
						>
							{#each ACTIONS as opt}
								<option value={opt.value}>{opt.label}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="flex flex-col gap-1">
					<Label for="rule-subject">{irisT("Subject regex (optional)", $irisLocale)}</Label>
					<Input
						id="rule-subject"
						class="h-7 font-mono text-xs"
						placeholder={irisT("^\\\\[ALERT\\\\]", $irisLocale)}
						value={editing.match_subject_regex ?? ''}
						oninput={(e) =>
							(editing!.match_subject_regex = (e.currentTarget as HTMLInputElement).value || null)}
					/>
				</div>

				<div class="flex flex-col gap-1">
					<Label for="rule-from">{irisT("From regex (optional)", $irisLocale)}</Label>
					<Input
						id="rule-from"
						class="h-7 font-mono text-xs"
						placeholder={irisT("@example\\\\.com$", $irisLocale)}
						value={editing.match_from_regex ?? ''}
						oninput={(e) =>
							(editing!.match_from_regex = (e.currentTarget as HTMLInputElement).value || null)}
					/>
				</div>

				<div class="flex flex-col gap-1">
					<Label for="rule-to">{irisT("To regex (optional)", $irisLocale)}</Label>
					<Input
						id="rule-to"
						class="h-7 font-mono text-xs"
						placeholder={irisT("^abuse@", $irisLocale)}
						value={editing.match_to_regex ?? ''}
						oninput={(e) =>
							(editing!.match_to_regex = (e.currentTarget as HTMLInputElement).value || null)}
					/>
				</div>

				<label class="flex cursor-pointer items-center gap-2">
					<Switch
						checked={!!editing.enabled}
						onCheckedChange={(v: boolean) => (editing!.enabled = v)}
					/>
					<span class="text-xs">{irisT("Enabled", $irisLocale)}</span>
				</label>

				{#if editError}
					<p class="text-2xs text-destructive">{editError}</p>
				{/if}
			</div>
		{/if}

		<Dialog.Footer>
			<Button variant="outline" onclick={() => (editing = null)} disabled={saving}>{irisT("Cancel", $irisLocale)}</Button>
			<Button onclick={submitEdit} disabled={saving}>
				{saving ? irisT("Saving…", $irisLocale) : editing?.id ? irisT("Save", $irisLocale) : irisT("Create rule", $irisLocale)}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
