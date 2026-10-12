<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { type AlertResolution } from '$lib/services/alert-resolutions.service';
	import { type AlertStatus } from '$lib/services/alert-status.service';
	import { type CaseClassification } from '$lib/services/case-classifications.service';
	import { type Severity } from '$lib/services/severities.service';
	import { type Customer } from '$lib/services/customers.service';
	import { type MentionableUser } from '$lib/services/users.service';
	import Button from '$lib/components/ui/button/button.svelte';
	import Input from '$lib/components/ui/input/input.svelte';
	import SearchSelect, {
		type SelectOption
	} from '$lib/components/common/selects/SearchSelect.svelte';
	import { SaveAlertFiltersModal, defaultFilters, type Filters } from '.';
	import CustomConditionsPanel from './CustomConditionsPanel.svelte';

	type Preset = {
		filter_id: number;
		filter_name: string;
	};

	type SaveMeta = {
		name: string;
		description: string;
		isPrivate: boolean;
	};

	type Props = {
		value: Filters;
		onChange: (next: Filters) => void;
		onApply: () => void;
		onClear?: () => void;
		/**
		 * The part of the search expression this form cannot render —
		 * alternations, negations, wildcards, JSON paths.
		 *
		 * Shown read-only rather than hidden: it is still narrowing the
		 * queue, and the fields below would otherwise look like the whole
		 * story. It survives every edit made here untouched.
		 */
		residue?: string;
		presets?: Preset[];
		selectedPresetId?: string;
		onPresetSelect?: (id: number) => void;
		onSaveAsFilter?: (filters: Filters, meta: SaveMeta) => void;
		saving?: boolean;
		alertResolutions: AlertResolution[];
		alertStatuses: AlertStatus[];
		caseClassifications: CaseClassification[];
		severities: Severity[];
		customers: Customer[];
		owners: MentionableUser[];
	};

	let {
		value,
		onChange,
		onApply,
		onClear,
		residue = '',
		presets = [],
		onSaveAsFilter,
		saving = false,
		alertResolutions,
		alertStatuses,
		caseClassifications,
		severities,
		customers,
		owners
	}: Props = $props();

	const strOrUndef = (v: string): string | undefined => {
		const s = v.trim();
		return s === '' ? undefined : s;
	};

	const numOrUndef = (v: string): number | undefined => {
		const s = v.trim();
		if (s === '') return undefined;
		const n = Number(s);
		return Number.isFinite(n) ? n : undefined;
	};

	const setStr = (key: keyof Filters, v: string) => {
		onChange({ ...value, [key]: strOrUndef(v) });
	};

	const setNum = (key: keyof Filters, v: string) => {
		onChange({ ...value, [key]: numOrUndef(v) });
	};

	const clear = () => {
		if (onClear) {
			onClear();
			return;
		}
		onChange(defaultFilters());
	};

	let saveOpen = $state(false);
	let saveMeta = $state<SaveMeta>({ name: '', description: '', isPrivate: true });

	const openSave = () => {
		saveMeta = { name: '', description: '', isPrivate: true };
		saveOpen = true;
	};

	const doSave = () => {
		if (!onSaveAsFilter) return;
		if (saveMeta.name.trim() === '') return;

		saveOpen = false;

		onSaveAsFilter(value, saveMeta);
	};

	const submit = (e: SubmitEvent) => {
		e.preventDefault();
		onApply();
	};

	const resolutionOptions = $derived.by<SelectOption[]>(() =>
		alertResolutions.map((resolution) => ({
			value: String(resolution.resolution_status_id),
			label: resolution.resolution_status_name
		}))
	);

	const statusOptions = $derived.by<SelectOption[]>(() =>
		alertStatuses.map((status) => ({
			value: String(status.status_id),
			label: status.status_name
		}))
	);

	const customerOptions = $derived.by<SelectOption[]>(() =>
		customers.map((customer) => ({
			value: String(customer.customer_id),
			label: customer.customer_name
		}))
	);

	const ownerOptions = $derived.by<SelectOption[]>(() =>
		owners.map((owner) => ({
			value: String(owner.user_id),
			label: owner.user_name || owner.user_login
		}))
	);

	const classificationOptions = $derived.by<SelectOption[]>(() =>
		caseClassifications.map((c) => ({ value: String(c.id), label: c.name_expanded }))
	);

	const severityOptions = $derived.by<SelectOption[]>(() =>
		severities.map((s) => ({ value: String(s.severity_id), label: s.severity_name }))
	);
</script>

<form
	class="flex max-h-[70vh] w-full flex-col rounded-xl border bg-muted/100 shadow-sm"
	onsubmit={submit}
>
	<div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
		<div class="grid grid-cols-2 gap-x-3 gap-y-3 md:grid-cols-4">
			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Title", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Filter by title...", $irisLocale)}
					value={value.alert_title ?? ''}
					oninput={(e) => setStr('alert_title', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Description", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Filter by description...", $irisLocale)}
					value={value.alert_description ?? ''}
					oninput={(e) => setStr('alert_description', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Source", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Filter by source...", $irisLocale)}
					value={value.alert_source ?? ''}
					oninput={(e) => setStr('alert_source', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Tags", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Filter by tags...", $irisLocale)}
					value={typeof value.alert_tags === 'string' ? value.alert_tags : ''}
					oninput={(e) => setStr('alert_tags', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
		</div>

		<hr class="border-border/50" />

		<div class="grid grid-cols-2 gap-x-3 gap-y-3 md:grid-cols-4">
			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Status", $irisLocale)}</div>
				<SearchSelect
					size="sm"
					value={value.alert_status_id == null ? '' : String(value.alert_status_id)}
					options={statusOptions}
					placeholder={irisT("Status", $irisLocale)}
					searchPlaceholder="Search status..."
					onChange={(next) =>
						onChange({
							...value,
							alert_status_id: next ? Number(next) : undefined
						})}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Severity", $irisLocale)}</div>
				<SearchSelect
					size="sm"
					value={value.alert_severity_id == null ? '' : String(value.alert_severity_id)}
					options={severityOptions}
					placeholder={irisT("Severity", $irisLocale)}
					searchPlaceholder="Search severity..."
					onChange={(next) =>
						onChange({
							...value,
							alert_severity_id: next ? Number(next) : undefined
						})}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Classification", $irisLocale)}</div>
				<SearchSelect
					size="sm"
					value={value.alert_classification_id == null ? '' : String(value.alert_classification_id)}
					options={classificationOptions}
					placeholder={irisT("Classification", $irisLocale)}
					searchPlaceholder="Search classification..."
					onChange={(next) =>
						onChange({
							...value,
							alert_classification_id: next ? Number(next) : undefined
						})}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Resolution Status", $irisLocale)}</div>
				<SearchSelect
					size="sm"
					value={value.resolution_status_id == null ? '' : String(value.resolution_status_id)}
					options={resolutionOptions}
					placeholder={irisT("Resolution Status", $irisLocale)}
					searchPlaceholder="Search resolution status..."
					onChange={(next) =>
						onChange({
							...value,
							resolution_status_id: next ? Number(next) : undefined
						})}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Customer", $irisLocale)}</div>
				<SearchSelect
					size="sm"
					value={value.alert_customer_id == null ? '' : String(value.alert_customer_id)}
					options={customerOptions}
					placeholder={irisT("Customer", $irisLocale)}
					searchPlaceholder="Search customer..."
					onChange={(next) =>
						onChange({
							...value,
							alert_customer_id: next ? Number(next) : undefined
						})}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Owner", $irisLocale)}</div>
				<SearchSelect
					size="sm"
					value={value.alert_owner_id == null ? '' : String(value.alert_owner_id)}
					options={ownerOptions}
					placeholder={irisT("Owner", $irisLocale)}
					searchPlaceholder="Search owner..."
					onChange={(next) =>
						onChange({
							...value,
							alert_owner_id: next ? Number(next) : undefined
						})}
				/>
			</div>
		</div>

		<hr class="border-border/50" />

		<div class="grid grid-cols-2 gap-x-3 gap-y-3 md:grid-cols-4">
			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Source Start Date", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					type="date"
					value={value.alert_start_date ?? ''}
					oninput={(e) => setStr('alert_start_date', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Source End Date", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					type="date"
					value={value.alert_end_date ?? ''}
					oninput={(e) => setStr('alert_end_date', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Creation Start Date", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					type="date"
					value={value.creation_start_date ?? ''}
					oninput={(e) =>
						setStr('creation_start_date', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Creation End Date", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					type="date"
					value={value.creation_end_date ?? ''}
					oninput={(e) => setStr('creation_end_date', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
		</div>

		<hr class="border-border/50" />

		<div class="grid grid-cols-2 gap-x-3 gap-y-3 md:grid-cols-4">
			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Asset(s) name", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Filter by asset...", $irisLocale)}
					value={typeof value.alert_assets === 'string' ? value.alert_assets : ''}
					oninput={(e) => setStr('alert_assets', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("IOC(s)", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Filter by IOC...", $irisLocale)}
					value={typeof value.alert_iocs === 'string' ? value.alert_iocs : ''}
					oninput={(e) => setStr('alert_iocs', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Alert(s) ID", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Alert IDs...", $irisLocale)}
					value={typeof value.alert_ids === 'string' ? value.alert_ids : ''}
					oninput={(e) => setStr('alert_ids', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Source Reference", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					placeholder={irisT("Source reference...", $irisLocale)}
					value={value.source_reference ?? ''}
					oninput={(e) => setStr('source_reference', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Case ID", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					inputmode="numeric"
					placeholder={irisT("Case ID", $irisLocale)}
					value={value.case_id == null ? '' : String(value.case_id)}
					oninput={(e) => setNum('case_id', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>

			<!--
			  AlertCluster linkage. Accepts an alert cluster id (positive number) or
			  `-1` to surface un-grouped alerts. Text input keeps the UI
			  consistent with the sibling Case ID field; typing "-1" is a
			  documented shortcut for "no alert cluster".
			-->
			<div class="space-y-0.5">
				<div class="text-xs text-muted-foreground">{irisT("Alert Cluster ID (-1 = none)", $irisLocale)}</div>
				<Input
					class="h-8 text-xs"
					inputmode="numeric"
					placeholder={irisT("Alert Cluster ID or -1", $irisLocale)}
					value={value.cluster_id == null ? '' : String(value.cluster_id)}
					oninput={(e) => setNum('cluster_id', (e.currentTarget as HTMLInputElement).value)}
				/>
			</div>
		</div>

		<CustomConditionsPanel
			value={value.custom_conditions ?? undefined}
			onChange={(next) => onChange({ ...value, custom_conditions: next })}
		/>

		{#if residue.trim() !== ''}
			<div class="space-y-1 rounded-lg border border-dashed border-border/70 bg-background/50 p-3">
				<div class="text-xs text-muted-foreground">
					{irisT("Also applied, from the search bar — edit it there", $irisLocale)}
				</div>
				<code class="block break-all font-mono text-xs">{residue}</code>
			</div>
		{/if}
	</div>

	<div class="flex shrink-0 items-center justify-between border-t border-border/50 px-5 py-4">
		<div class="flex gap-2">
			<Button type="submit" size="sm">{irisT("Apply Filters", $irisLocale)}</Button>
			<Button type="button" size="sm" variant="outline" onclick={clear}>{irisT("Clear", $irisLocale)}</Button>
		</div>

		{#if presets.length > 0 || onSaveAsFilter}
			<div class="flex items-center gap-2">
				{#if onSaveAsFilter}
					<Button type="button" size="sm" variant="outline" disabled={saving} onclick={openSave}>
						{irisT("Save as filter", $irisLocale)}
					</Button>
				{/if}
			</div>
		{/if}
	</div>

	{#if onSaveAsFilter}
		<SaveAlertFiltersModal
			open={saveOpen}
			onOpenChange={(v) => (saveOpen = v)}
			value={saveMeta}
			onChange={(next) => (saveMeta = next)}
			disabled={saving}
			onSave={doSave}
		/>
	{/if}
</form>
