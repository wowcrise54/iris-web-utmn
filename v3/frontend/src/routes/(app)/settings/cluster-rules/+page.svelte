<!--
  Cluster-rules admin. Rules stack alerts into alert clusters.

  Investigation-flow attachment is authored on the *flow* itself (see
  /settings/investigation-flows) — this page focuses purely on the
  stacking action.

  Conditions are edited through the shared ConditionsBuilder (nested
  AND/OR groups); dry-run previews matches against the last 30 days.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { onMount } from 'svelte';
	import { FilterIcon, PlayIcon, PlusIcon, RocketIcon, Trash2Icon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import ConfirmationDialog from '$lib/components/ui/dialog/ConfirmationDialog.svelte';
	import { Input } from '$lib/components/ui/input';
	import { Loading } from '$lib/components/ui/loading';
	import { toast } from '$lib/components/ui/toast';
	import ConditionsBuilder, {
		emptyRootGroup,
		type GroupNode
	} from '$lib/components/common/ConditionsBuilder/ConditionsBuilder.svelte';
	import {
		ClusterRulesService,
		type BackfillRuleResponse
	} from '$lib/services/cluster-rules.service';
	import type { ClusterRule } from '$lib/types/resources/cluster-rule';

	let rules = $state<ClusterRule[]>([]);
	let loading = $state(false);
	let editing = $state<ClusterRule | null>(null);
	let conditionsTree = $state<GroupNode>(emptyRootGroup());
	let timeWindowSeconds = $state<number | null>(null);
	let groupByCsv = $state('');
	let titleTemplate = $state('');
	let testMatches = $state<number[] | null>(null);

	// Common correlation entities. `field` matches the backend's group_by
	// vocabulary — the same DSL `apply_custom_conditions` uses, so
	// relationship-joined paths (`assets.asset_name`) are valid.
	const CORRELATION_PRESETS = [
		{ label: irisT("Same host", $irisLocale), field: 'assets.asset_name' },
		{ label: irisT("Same IP", $irisLocale), field: 'assets.asset_ip' },
		{ label: irisT("Same user (owner)", $irisLocale), field: 'alert_owner_id' },
		{ label: irisT("Same source", $irisLocale), field: 'alert_source' },
		{ label: irisT("Same title", $irisLocale), field: 'alert_title' },
		{ label: irisT("Same IOC", $irisLocale), field: 'iocs.ioc_value' }
	];

	const splitCsv = (csv: string): string[] =>
		csv
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean);

	const groupByHasField = (csv: string, field: string): boolean => splitCsv(csv).includes(field);

	const toggleGroupByField = (csv: string, field: string): string => {
		const list = splitCsv(csv);
		const idx = list.indexOf(field);
		if (idx === -1) list.push(field);
		else list.splice(idx, 1);
		return list.join(', ');
	};

	let deleteOpen = $state(false);
	let ruleToDelete = $state<ClusterRule | null>(null);

	let backfillOpen = $state(false);
	let backfilling = $state(false);

	// How many days of history Test / Back-fill consider. 30 matches
	// the backend default; kept editable so analysts can widen or narrow
	// the window per rule as they iterate.
	let sampleDays = $state<number>(30);

	const showError = (msg: string, detail?: string) =>
		toast({ title: msg, description: detail, variant: 'destructive' });
	const showSuccess = (msg: string) => toast({ title: msg, variant: 'success' });

	const load = async () => {
		loading = true;
		try {
			const res = await ClusterRulesService.list();
			if (!res.ok) {
				showError('Failed to load rules', res.error?.message);
				return;
			}

			rules = (res.data as ClusterRule[]) ?? [];
		} finally {
			loading = false;
		}
	};

	const startEdit = (rule: ClusterRule | null) => {
		editing = rule ?? {
			rule_id: 0,
			rule_uuid: '',
			rule_name: 'New rule',
			rule_description: '',
			rule_is_active: true,
			rule_priority: 100,
			rule_customer_scope: null,
			rule_conditions: { logic: 'and', conditions: [] },
			rule_action_type: 'create_cluster',
			rule_action_config: {},
			rule_created_at: '',
			rule_updated_at: ''
		};
		// Rebuild the builder tree from the persisted conditions. Fresh
		// rules start with an empty AND group so the analyst can add the
		// first row.
		const c = editing.rule_conditions ?? { logic: 'and', conditions: [] };
		conditionsTree = {
			logic: (c.logic as 'and' | 'or') ?? 'and',
			conditions: (c.conditions as GroupNode['conditions']) ?? []
		};
		timeWindowSeconds =
			(editing.rule_conditions as unknown as { time_window_seconds?: number })
				?.time_window_seconds ?? null;
		const gb = (editing.rule_conditions as unknown as { group_by?: string[] })?.group_by;
		groupByCsv = Array.isArray(gb) ? gb.join(', ') : '';
		titleTemplate = (editing.rule_action_config?.title_template as string) ?? '';
		testMatches = null;
	};

	const save = async () => {
		if (!editing) return;
		if (conditionsTree.conditions.length === 0) {
			showError('Add at least one condition');
			return;
		}
		const body = {
			rule_name: editing.rule_name,
			rule_description: editing.rule_description ?? '',
			rule_is_active: editing.rule_is_active,
			rule_priority: editing.rule_priority,
			rule_customer_scope: editing.rule_customer_scope,
			rule_conditions: {
				logic: conditionsTree.logic,
				conditions: conditionsTree.conditions,
				...(timeWindowSeconds && timeWindowSeconds > 0
					? { time_window_seconds: timeWindowSeconds }
					: {}),
				...(groupByCsv.trim()
					? {
							group_by: groupByCsv
								.split(',')
								.map((s) => s.trim())
								.filter(Boolean)
						}
					: {})
			},
			rule_action_type: 'create_cluster' as const,
			rule_action_config: {
				...(titleTemplate ? { title_template: titleTemplate } : {})
			}
		};
		const isNew = editing.rule_id === 0;
		const res = isNew
			? await ClusterRulesService.create(body)
			: await ClusterRulesService.update(editing.rule_id, body);
		if (!res.ok) {
			showError(isNew ? 'Failed to create rule' : 'Failed to save rule', res.error?.message);
			return;
		}

		editing = null;
		await load();
		showSuccess(isNew ? 'Rule created' : 'Rule updated');
	};

	const askDelete = (rule: ClusterRule) => {
		ruleToDelete = rule;
		deleteOpen = true;
	};

	const confirmDelete = async () => {
		if (!ruleToDelete) return;

		const res = await ClusterRulesService.remove(ruleToDelete.rule_id);
		if (!res.ok) {
			showError('Failed to delete rule', res.error?.message);
			return;
		}

		ruleToDelete = null;
		await load();
		showSuccess('Rule deleted');
	};

	const runTest = async () => {
		if (!editing || editing.rule_id === 0) {
			showError('Save the rule first — Test runs against the saved rule');
			return;
		}
		const res = await ClusterRulesService.test(editing.rule_id, {
			sample_days: sampleDays
		});
		if (!res.ok) {
			showError('Test failed', res.error?.message);
			return;
		}

		testMatches = (res.data as { matching_alert_ids?: number[] })?.matching_alert_ids ?? [];
	};

	const runBackfill = async () => {
		if (!editing || editing.rule_id === 0) return;
		backfilling = true;
		try {
			const res = await ClusterRulesService.backfill(editing.rule_id, {
				sample_days: sampleDays
			});
			if (!res.ok) {
				showError('Back-fill failed', res.error?.message);
				return;
			}

			const payload =
				res.data && typeof res.data === 'object' ? (res.data as BackfillRuleResponse) : null;
			if (!payload) {
				showError('Back-fill failed', 'The server returned an unexpected response.');
				return;
			}

			const parts: string[] = [];
			if (payload.attached) parts.push(`${payload.attached} attached`);
			if (payload.skipped_already_in_cluster)
				parts.push(`${payload.skipped_already_in_cluster} skipped (already in cluster)`);
			if (payload.errors) parts.push(`${payload.errors} error(s)`);
			const summary = parts.length
				? parts.join(' · ')
				: `Considered ${payload.considered} — no changes`;
			showSuccess(summary);
		} finally {
			backfilling = false;
			backfillOpen = false;
		}
	};

	onMount(load);
</script>

<svelte:head>
	<title>{irisT("Clustering Rules", $irisLocale)}</title>
</svelte:head>

<div class="flex h-full min-h-0 w-full flex-col gap-4 p-4">
	<header class="flex items-center justify-between border-b pb-3">
		<div class="flex items-center gap-2">
			<FilterIcon class="h-5 w-5 text-muted-foreground" />
			<div>
				<h1 class="text-base font-semibold">{irisT("Clustering Rules", $irisLocale)}</h1>
				<p class="text-2xs uppercase tracking-wide text-muted-foreground">
					{irisT("Auto-stack alerts into alert clusters on match", $irisLocale)}
				</p>
			</div>
		</div>
		<Button onclick={() => startEdit(null)}>
			<PlusIcon class="mr-2 h-4 w-4" /> {irisT("New rule", $irisLocale)}
		</Button>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
		{#if loading}
			<Loading />
		{:else if rules.length === 0}
			<p class="text-sm text-muted-foreground">
				{irisT("No rules yet. Create one to auto-group repeat alerts into a single cluster.", $irisLocale)}
			</p>
		{:else}
			<div class="overflow-hidden rounded-md border">
				<table class="w-full text-sm">
					<thead class="bg-muted/40">
						<tr class="text-left">
							<th class="px-3 py-2 text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Name", $irisLocale)}</th>
							<th class="px-3 py-2 text-2xs uppercase tracking-wide text-muted-foreground"
								>{irisT("Priority", $irisLocale)}</th
							>
							<th class="px-3 py-2 text-2xs uppercase tracking-wide text-muted-foreground"
								>{irisT("Active", $irisLocale)}</th
							>
							<th class="px-3 py-2"></th>
						</tr>
					</thead>
					<tbody>
						{#each rules as rule (rule.rule_id)}
							<tr class="border-t hover:bg-muted/20">
								<td class="px-3 py-2">
									<button
										type="button"
										class="text-left font-medium hover:underline"
										onclick={() => startEdit(rule)}
									>
										{rule.rule_name}
									</button>
									{#if rule.rule_description}
										<p class="text-xs text-muted-foreground">{rule.rule_description}</p>
									{/if}
								</td>
								<td class="px-3 py-2 text-xs">{rule.rule_priority}</td>
								<td class="px-3 py-2 text-xs">
									{#if rule.rule_is_active}
										<span class="rounded-full bg-green-500/10 px-2 py-0.5 text-green-600"
											>{irisT("Active", $irisLocale)}</span
										>
									{:else}
										<span class="rounded-full bg-muted px-2 py-0.5 text-muted-foreground"
											>{irisT("Disabled", $irisLocale)}</span
										>
									{/if}
								</td>
								<td class="px-3 py-2 text-right">
									<Button
										variant="ghost"
										size="icon"
										aria-label={irisT("Delete rule", $irisLocale)}
										onclick={() => askDelete(rule)}
									>
										<Trash2Icon class="h-4 w-4 text-destructive" />
									</Button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if editing}
			<section class="rounded-md border bg-card p-4 shadow-sm">
				<h2 class="mb-3 text-sm font-semibold">
					{editing.rule_id === 0 ? irisT("New rule", $irisLocale) : `Edit rule #${editing.rule_id}`}
				</h2>

				<div class="grid gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1">
						<label for="rule-name" class="text-2xs uppercase tracking-wide text-muted-foreground"
							>{irisT("Name", $irisLocale)}</label
						>
						<Input id="rule-name" bind:value={editing.rule_name} />
					</div>
					<div class="flex flex-col gap-1">
						<label for="rule-desc" class="text-2xs uppercase tracking-wide text-muted-foreground"
							>{irisT("Description", $irisLocale)}</label
						>
						<Input id="rule-desc" bind:value={editing.rule_description as string} />
					</div>
				</div>

				<div class="mt-3 grid gap-3 sm:grid-cols-3">
					<div class="flex flex-col gap-1">
						<label
							for="rule-priority"
							class="text-2xs uppercase tracking-wide text-muted-foreground">{irisT("Priority", $irisLocale)}</label
						>
						<Input id="rule-priority" type="number" bind:value={editing.rule_priority} />
					</div>
					<div class="flex items-end">
						<label class="inline-flex items-center gap-2 text-sm">
							<input type="checkbox" bind:checked={editing.rule_is_active} /> {irisT("Active", $irisLocale)}
						</label>
					</div>
				</div>

				<div class="mt-4">
					<p class="mb-2 text-2xs uppercase tracking-wide text-muted-foreground">
						{irisT("Match conditions", $irisLocale)}
					</p>
					<ConditionsBuilder bind:value={conditionsTree} target="alert" />
					<p class="mt-2 text-2xs text-muted-foreground">
						{irisT("JSON fields work with dotted paths — e.g.", $irisLocale)} <code class="rounded bg-muted px-1 py-0.5"
							>alert_context.severity</code
						>
						{irisT("drills into the JSON document at query time. Relationship paths like", $irisLocale)}
						<code class="rounded bg-muted px-1 py-0.5">assets.asset_name</code> {irisT("join the related table.", $irisLocale)}
					</p>
				</div>

				<!--
				  Correlation section — this is the load-bearing bit of a
				  rule. The engine already supports arbitrary group-by
				  fields, but analysts don't think in field names; they
				  think in entities ("same host", "same user"). The chips
				  below one-click those into the CSV that the backend
				  consumes verbatim, plus a free-text field for anything
				  the presets don't cover.
				-->
				<div class="mt-4 rounded-md border border-primary/20 bg-primary/5 p-3">
					<p class="mb-1 text-2xs font-semibold uppercase tracking-wide text-primary">
						{irisT("Correlation", $irisLocale)}
					</p>
					<p class="mb-3 text-xs text-muted-foreground">
						{irisT("Group matching alerts into", $irisLocale)} <em>{irisT("one alert cluster", $irisLocale)}</em> {irisT("when they share the same value on these\n\t\t\t\t\t\tfields, within the stacking window below. Example: 10 failed-login alerts from the same host\n\t\t\t\t\t\tin 5 minutes → one “Brute force on host X” cluster.", $irisLocale)}
					</p>
					<div class="mb-2 flex flex-wrap items-center gap-2">
						{#each CORRELATION_PRESETS as preset (preset.field)}
							{@const active = groupByHasField(groupByCsv, preset.field)}
							<button
								type="button"
								class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors {active
									? irisT("border-primary bg-primary text-primary-foreground", $irisLocale)
									: irisT("border-border bg-background hover:bg-muted", $irisLocale)}"
								onclick={() => (groupByCsv = toggleGroupByField(groupByCsv, preset.field))}
							>
								{preset.label}
								<span class="text-2xs opacity-70">({preset.field})</span>
							</button>
						{/each}
					</div>
					<div class="grid gap-3 sm:grid-cols-2">
						<div class="flex flex-col gap-1">
							<label
								for="rule-groupby"
								class="text-2xs uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Correlation keys (comma-separated)", $irisLocale)}
							</label>
							<Input
								id="rule-groupby"
								placeholder={irisT("e.g. alert_customer_id, assets.asset_name", $irisLocale)}
								bind:value={groupByCsv}
							/>
							<p class="text-2xs text-muted-foreground">
								{irisT("Tenant scope (", $irisLocale)}<code class="rounded bg-muted px-1">alert_customer_id</code>{irisT(") is added\n\t\t\t\t\t\t\t\tautomatically if you don't include it — an alert cluster never mixes tenants.", $irisLocale)}
							</p>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="rule-window"
								class="text-2xs uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Stacking window (seconds)", $irisLocale)}
							</label>
							<Input
								id="rule-window"
								type="number"
								placeholder="3600"
								bind:value={timeWindowSeconds}
							/>
							<p class="text-2xs text-muted-foreground">
								{irisT("Alerts that arrive within this window and match the correlation keys above stack\n\t\t\t\t\t\t\t\tinto the same cluster. Leave blank to stack forever (open alert cluster stays open).", $irisLocale)}
							</p>
						</div>
					</div>
				</div>

				<div class="mt-4 flex flex-col gap-1">
					<label for="rule-title" class="text-2xs uppercase tracking-wide text-muted-foreground">
						{irisT("AlertCluster title template (", $irisLocale)}{'{alert_title}'} {irisT("is substituted from the first alert)", $irisLocale)}
					</label>
					<Input
						id="rule-title"
						placeholder="Brute-force cluster: {'{alert_title}'}"
						bind:value={titleTemplate}
					/>
				</div>

				<div class="mt-4 flex flex-wrap items-center gap-3">
					<Button onclick={save}>{irisT("Save", $irisLocale)}</Button>
					<Button variant="outline" onclick={() => (editing = null)}>{irisT("Cancel", $irisLocale)}</Button>

					<!--
					  History window used by Test AND Back-fill. Kept as
					  one control on purpose — testing against a window
					  before back-filling on it is the usual workflow, so
					  a shared value avoids accidental mismatches.
					-->
					<div class="flex items-center gap-2 border-l pl-3">
						<label
							for="rule-sample-days"
							class="text-2xs uppercase tracking-wide text-muted-foreground"
						>
							{irisT("History window (days)", $irisLocale)}
						</label>
						<Input
							id="rule-sample-days"
							type="number"
							min="1"
							class="w-24"
							bind:value={sampleDays}
						/>
					</div>

					<Button variant="ghost" onclick={runTest}>
						<PlayIcon class="mr-2 h-4 w-4" /> {irisT("Test", $irisLocale)}
					</Button>
					<Button
						variant="outline"
						disabled={!editing || editing.rule_id === 0 || backfilling}
						onclick={() => (backfillOpen = true)}
					>
						<RocketIcon class="mr-2 h-4 w-4" />
						{backfilling ? irisT("Backfilling…", $irisLocale) : irisT("Back-fill previous alerts", $irisLocale)}
					</Button>
					{#if testMatches !== null}
						<span class="text-xs text-muted-foreground">
							{irisT("Matched", $irisLocale)} {testMatches.length} {irisT("alert(s) from the last", $irisLocale)} {sampleDays} {irisT("day", $irisLocale)}{sampleDays === 1
								? ''
								: 's'}
						</span>
					{/if}
				</div>
			</section>
		{/if}
	</div>
</div>

<ConfirmationDialog
	bind:open={deleteOpen}
	title={irisT("Delete rule?", $irisLocale)}
	message={ruleToDelete
		? irisT("Delete rule \"{name}\"? This cannot be undone.", $irisLocale, { name: ruleToDelete.rule_name })
		: irisT("Delete this rule?", $irisLocale)}
	confirmText="Delete"
	confirmButtonVariant="destructive"
	onConfirm={confirmDelete}
/>

<ConfirmationDialog
	bind:open={backfillOpen}
	title={irisT("Back-fill previous alerts?", $irisLocale)}
	message={irisT("Apply this rule to matching alerts from the last {days} days. Alerts already grouped into an alert cluster are skipped. The stacking window and grouping keys prevent duplicates on repeated runs.", $irisLocale, { days: sampleDays })}
	confirmText="Back-fill"
	confirmButtonVariant="default"
	onConfirm={runBackfill}
/>
