<!--
  Create / edit a registry entry.

  Customer and asset type are only editable while creating. Together
  with the normalized name they *are* the dedup identity: changing
  either on an existing row would silently re-home the asset and orphan
  its audit trail, so the backend strips both from update payloads and
  the form doesn't pretend otherwise.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import * as Dialog from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import CustomAttributesSection from '$lib/components/common/CustomAttributes/CustomAttributesSection.svelte';
	import TagInput from '$lib/components/common/tag/TagInput.svelte';
	import SearchSelect from '$lib/components/common/selects/SearchSelect.svelte';
	import type { AssetType } from '$lib/services/asset-types.service';
	import type { Customer } from '$lib/services/customers.service';
	import type {
		AssetCriticality,
		AssetEnvironment,
		CreateManagedAssetBody,
		ManagedAsset,
		UpdateManagedAssetBody
	} from '$lib/types/resources/managed-asset';

	type Props = {
		open: boolean;
		/** Null while creating. */
		asset?: ManagedAsset | null;
		customers: Customer[];
		assetTypes: AssetType[];
		saving?: boolean;
		onCreate: (body: CreateManagedAssetBody) => Promise<void>;
		onUpdate: (id: number, body: UpdateManagedAssetBody) => Promise<void>;
	};

	let {
		open = $bindable(false),
		asset = null,
		customers,
		assetTypes,
		saving = false,
		onCreate,
		onUpdate
	}: Props = $props();

	const CRITICALITIES: AssetCriticality[] = ['critical', 'high', 'medium', 'low', 'unknown'];
	const ENVIRONMENTS: AssetEnvironment[] = [
		'production',
		'staging',
		'development',
		'test',
		'dr',
		'unknown'
	];

	const editing = $derived(asset !== null);

	const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

	// `SearchSelect` types its callback for the multi-select case as well;
	// every picker here is single-select, so the value is always a string.
	const single = (value: string | string[]) => (Array.isArray(value) ? (value[0] ?? '') : value);

	const customerOptions = $derived(
		customers.map((customer) => ({
			value: String(customer.customer_id),
			label: customer.customer_name
		}))
	);
	const assetTypeOptions = $derived(
		assetTypes.map((type) => ({ value: String(type.asset_id), label: type.asset_name }))
	);
	const CRITICALITY_OPTIONS = CRITICALITIES.map((value) => ({ value, label: titleCase(value) }));
	// An empty value is a real choice here — the column is nullable — so
	// it gets its own row rather than a separate clear affordance.
	const ENVIRONMENT_OPTIONS = [
		{ value: '', label: irisT("Not set", $irisLocale) },
		...ENVIRONMENTS.map((value) => ({ value, label: titleCase(value) }))
	];

	let clientId = $state<number | null>(null);
	let assetTypeId = $state<number | null>(null);
	let name = $state('');
	let description = $state('');
	let criticality = $state<AssetCriticality>('unknown');
	let environment = $state<AssetEnvironment | ''>('');
	let owner = $state('');
	let location = $state('');
	let tags = $state('');
	let ip = $state('');
	let domain = $state('');
	let isActive = $state(true);
	let customAttributes = $state<Record<string, Record<string, unknown>>>({});
	let error = $state<string | null>(null);

	// Reset the form whenever the dialog is (re)opened, so a create that
	// follows an edit doesn't inherit the previous row's values.
	$effect(() => {
		if (!open) return;
		error = null;
		clientId = asset?.client_id ?? (customers.length === 1 ? customers[0].customer_id : null);
		assetTypeId = asset?.asset_type_id ?? null;
		name = asset?.name ?? '';
		description = asset?.description ?? '';
		criticality = asset?.criticality ?? 'unknown';
		environment = asset?.environment ?? '';
		owner = asset?.owner ?? '';
		location = asset?.location ?? '';
		tags = asset?.tags ?? '';
		ip = asset?.ip ?? '';
		domain = asset?.domain ?? '';
		isActive = asset?.is_active ?? true;
		customAttributes = {};
	});

	const trimmedOrNull = (value: string) => {
		const trimmed = value.trim();
		return trimmed === '' ? null : trimmed;
	};

	const submit = async () => {
		error = null;

		if (!name.trim()) {
			error = 'A name is required.';
			return;
		}

		const shared = {
			name: name.trim(),
			description: trimmedOrNull(description),
			criticality,
			environment: environment === '' ? null : environment,
			owner: trimmedOrNull(owner),
			location: trimmedOrNull(location),
			tags: trimmedOrNull(tags),
			ip: trimmedOrNull(ip),
			domain: trimmedOrNull(domain),
			is_active: isActive,
			custom_attributes: customAttributes
		};

		if (editing && asset) {
			await onUpdate(asset.managed_asset_id, shared);
			return;
		}

		if (clientId === null) {
			error = 'A customer is required.';
			return;
		}
		if (assetTypeId === null) {
			error = 'An asset type is required.';
			return;
		}

		await onCreate({ ...shared, client_id: clientId, asset_type_id: assetTypeId });
	};
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="flex max-h-[90vh] flex-col overflow-y-auto p-0 sm:max-w-2xl">
		<Dialog.Header class="border-b px-6 py-4">
			<Dialog.Title class="text-base font-medium">
				{editing ? irisT("Edit asset", $irisLocale) : irisT("New asset", $irisLocale)}
			</Dialog.Title>
			<Dialog.Description class="text-xs">
				{editing
					? irisT("Customer and type are fixed — they are part of the asset identity.", $irisLocale)
					: irisT("Names are deduplicated per customer and type, ignoring case and extra spaces.", $irisLocale)}
			</Dialog.Description>
		</Dialog.Header>

		<div class="flex flex-col gap-4 px-6 py-5">
			<div class="grid gap-4 sm:grid-cols-2">
				<div class="flex flex-col gap-1.5">
					<Label>{irisT("Customer", $irisLocale)}</Label>
					<SearchSelect
						value={clientId === null ? '' : String(clientId)}
						options={customerOptions}
						placeholder={irisT("Select a customer…", $irisLocale)}
						searchPlaceholder="Search customers…"
						disabled={editing}
						onChange={(value) => {
							const raw = single(value);
							clientId = raw === '' ? null : Number(raw);
						}}
					/>
				</div>

				<div class="flex flex-col gap-1.5">
					<Label>{irisT("Type", $irisLocale)}</Label>
					<SearchSelect
						value={assetTypeId === null ? '' : String(assetTypeId)}
						options={assetTypeOptions}
						placeholder={irisT("Select a type…", $irisLocale)}
						searchPlaceholder="Search asset types…"
						disabled={editing}
						onChange={(value) => {
							const raw = single(value);
							assetTypeId = raw === '' ? null : Number(raw);
						}}
					/>
				</div>
			</div>

			<div class="flex flex-col gap-1.5">
				<Label for="asset-name">{irisT("Name", $irisLocale)}</Label>
				<Input id="asset-name" bind:value={name} placeholder={irisT("SRV-DC01", $irisLocale)} />
			</div>

			<div class="flex flex-col gap-1.5">
				<Label for="asset-description">{irisT("Description", $irisLocale)}</Label>
				<Textarea id="asset-description" bind:value={description} rows={3} />
			</div>

			<div class="grid gap-4 sm:grid-cols-2">
				<div class="flex flex-col gap-1.5">
					<Label>{irisT("Criticality", $irisLocale)}</Label>
					<SearchSelect
						value={criticality}
						options={CRITICALITY_OPTIONS}
						placeholder={irisT("Select a criticality…", $irisLocale)}
						searchPlaceholder="Search criticalities…"
						onChange={(value) => (criticality = single(value) as AssetCriticality)}
					/>
				</div>

				<div class="flex flex-col gap-1.5">
					<Label>{irisT("Environment", $irisLocale)}</Label>
					<SearchSelect
						value={environment}
						options={ENVIRONMENT_OPTIONS}
						placeholder={irisT("Not set", $irisLocale)}
						searchPlaceholder="Search environments…"
						onChange={(value) => (environment = single(value) as AssetEnvironment | '')}
					/>
				</div>

				<div class="flex flex-col gap-1.5">
					<Label for="asset-owner">{irisT("Owner", $irisLocale)}</Label>
					<Input id="asset-owner" bind:value={owner} />
				</div>

				<div class="flex flex-col gap-1.5">
					<Label for="asset-location">{irisT("Location", $irisLocale)}</Label>
					<Input id="asset-location" bind:value={location} />
				</div>

				<div class="flex flex-col gap-1.5">
					<Label for="asset-ip">{irisT("IP", $irisLocale)}</Label>
					<Input id="asset-ip" bind:value={ip} />
				</div>

				<div class="flex flex-col gap-1.5">
					<Label for="asset-domain">{irisT("Domain", $irisLocale)}</Label>
					<Input id="asset-domain" bind:value={domain} />
				</div>
			</div>

			<div class="flex flex-col gap-1.5">
				<Label for="asset-tags">{irisT("Tags", $irisLocale)}</Label>
				<TagInput bind:tags outputFormat="string" placeholder={irisT("Add tags...", $irisLocale)} maxTags={20} />
			</div>

			<label class="flex items-center gap-2 text-sm">
				<input type="checkbox" bind:checked={isActive} class="h-4 w-4 rounded border-input" />
				{irisT("Active", $irisLocale)}
			</label>

			<CustomAttributesSection
				objectType="managed_asset"
				existing={asset?.custom_attributes as Record<string, Record<string, unknown>> | null}
				bind:values={customAttributes}
			/>

			{#if error}
				<p class="text-xs text-destructive">{error}</p>
			{/if}
		</div>

		<div class="flex justify-end gap-2 border-t px-6 py-4">
			<Button variant="outline" onclick={() => (open = false)} disabled={saving}>{irisT("Cancel", $irisLocale)}</Button>
			<Button onclick={submit} disabled={saving}>
				{saving ? irisT("Saving…", $irisLocale) : editing ? irisT("Save changes", $irisLocale) : irisT("Create asset", $irisLocale)}
			</Button>
		</div>
	</Dialog.Content>
</Dialog.Root>
