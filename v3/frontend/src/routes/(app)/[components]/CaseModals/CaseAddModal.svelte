<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { UploadIcon } from 'lucide-svelte';
	import * as Dialog from '$lib/components/ui/dialog';
	import type { CreateCaseBody } from '$lib/services/case.service';
	import { CASES_CTX, type CasesContext } from '$lib/contexts/cases.context.svelte';
	import {
		CASE_TEMPLATES_CTX,
		type CaseTemplatesContext
	} from '$lib/contexts/case-templates.context.svelte';
	import SearchSelect, {
		type SelectOption
	} from '$lib/components/common/selects/SearchSelect.svelte';
	import CustomerPicker from '$lib/components/common/selects/CustomerPicker.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import {
		CaseClassificationsService,
		type CaseClassification
	} from '$lib/services/case-classifications.service';
	import type { RequestResponse } from '$lib/services/api.service';

	type CaseAddModalProps = {
		open: boolean;
		onOpenChange: (open: boolean) => void;
	};

	let { open, onOpenChange }: CaseAddModalProps = $props();

	const cases = getContext<CasesContext>(CASES_CTX);
	const caseTemplates = getContext<CaseTemplatesContext>(CASE_TEMPLATES_CTX);

	let classifications = $state<CaseClassification[]>([]);

	let customerId = $state('');
	let caseName = $state('');
	let caseTemplateId = $state('');
	let classificationId = $state('');
	let shortDescription = $state('');
	let socTicketId = $state('');

	let submitting = $state(false);
	let error = $state<string | null>(null);

	const classificationOptions = $derived.by<SelectOption[]>(() =>
		classifications.map((c) => ({ value: String(c.id), label: c.name_expanded }))
	);

	const templateOptions = $derived.by<SelectOption[]>(() =>
		caseTemplates.caseTemplates.map((t) => ({
			value: String(t.id),
			label: t.display_name || t.name
		}))
	);

	onMount(async () => {
		// `ApiService` resolves a failed request to `{ data: null, error, ok: false }`
		// rather than throwing, so the outer `.data` is null whenever this call
		// does not succeed. The app layout mounts this modal on every route,
		// including the unauthenticated boot where the classifications request
		// 401s — so the unguarded double-unwrap threw
		// "Cannot read properties of null (reading 'data')" as an unhandled
		// rejection on every logged-out load. Guard both levels of the envelope.
		const response = await CaseClassificationsService.list();
		const envelope = response.data as unknown as RequestResponse<CaseClassification[]> | null;

		classifications = (envelope?.data ?? []) as CaseClassification[];
	});

	// Templates are also created from Settings, which writes through its own
	// service rather than this context, and the app layout only loads them
	// once at mount. Refresh on open so anything added since is picked up
	// without a full page reload.
	$effect(() => {
		if (!open) return;

		void caseTemplates.refresh();
	});

	$effect(() => {
		if (open) return;

		customerId = '';
		caseName = '';
		caseTemplateId = '';
		classificationId = '';
		shortDescription = '';
		socTicketId = '';
		error = null;
		submitting = false;
	});

	// This modal builds a case from scratch. Someone who arrived holding an
	// archive from another instance wants the import wizard instead, and
	// shouldn't have to back out of here and go hunting for it.
	const openImport = async () => {
		onOpenChange(false);
		await goto('/cases/import');
	};

	const onSubmit = async (event: SubmitEvent) => {
		event.preventDefault();
		if (submitting) return;

		error = null;

		const cid = Number(customerId);
		if (!Number.isFinite(cid) || cid <= 0) {
			error = 'Customer is required';
			return;
		}

		const name = caseName.trim();
		if (name === '') {
			error = 'Case name is required';
			return;
		}

		const desc = shortDescription.trim();
		if (desc === '') {
			error = 'Short description is required';
			return;
		}

		const body: CreateCaseBody = {
			case_name: name,
			case_description: desc,
			case_customer_id: cid,
			case_soc_id: socTicketId.trim()
		};

		if (caseTemplateId !== '') body.case_template_id = Number(caseTemplateId);
		if (classificationId !== '') body.classification_id = Number(classificationId);

		const created = await cases.create(body);

		if (!created) {
			error = 'Faled to create case';

			return;
		}

		onOpenChange(false);

		await goto(`/case/${created.case_id}`);
	};
</script>

<Dialog.Root bind:open {onOpenChange}>
	<Dialog.Content
		class="flex max-h-[calc(100dvh-2rem)] w-[min(720px,calc(100dvw-2rem))] max-w-none flex-col overflow-auto p-0"
	>
		<Dialog.Header class="border-b px-8 py-6">
			<Dialog.Title class="text-xl font-semibold">{irisT("Create a new case", $irisLocale)}</Dialog.Title>
		</Dialog.Header>

		<div class="flex w-full flex-col px-8">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<p class="text-sm text-muted-foreground">{irisT("Fields with an asterisk are required.", $irisLocale)}</p>
				<button
					type="button"
					class="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
					onclick={openImport}
				>
					<UploadIcon size={14} />
					{irisT("Import from IRIS export", $irisLocale)}
				</button>
			</div>
			<p class="mt-2 text-sm text-muted-foreground">
				{irisT("Access to the case can be granted to other users once the case is created. Users pertaining\n\t\t\t\tto the customer will be able to see the case by default.", $irisLocale)}
			</p>

			<form class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2" onsubmit={onSubmit}>
				<div class="flex flex-col gap-2">
					<div class="text-sm font-medium">{irisT("Case name *", $irisLocale)}</div>
					<Input class="text-sm" autocomplete="off" bind:value={caseName} />
				</div>

				<div class="flex flex-col gap-2">
					<div class="text-sm font-medium">{irisT("SOC ticket ID", $irisLocale)}</div>
					<Input
						class="bg-background text-sm outline-none"
						autocomplete="off"
						bind:value={socTicketId}
					/>
				</div>

				<div class="flex flex-col gap-2">
					<div class="text-sm font-medium">{irisT("Case template", $irisLocale)}</div>
					<SearchSelect
						value={caseTemplateId}
						options={templateOptions}
						placeholder={irisT("Select case template", $irisLocale)}
						searchPlaceholder="Search template..."
						onChange={(value) => (caseTemplateId = value as string)}
					/>
				</div>

				<div class="flex flex-col gap-2">
					<div class="text-sm font-medium">{irisT("Classification", $irisLocale)}</div>
					<SearchSelect
						value={classificationId}
						options={classificationOptions}
						placeholder={irisT("Select classification", $irisLocale)}
						searchPlaceholder="Search classification..."
						onChange={(value) => (classificationId = value as string)}
					/>
				</div>

				<div class="flex flex-col gap-2">
					<div class="text-sm font-medium">{irisT("Customer *", $irisLocale)}</div>
					<CustomerPicker value={customerId} onChange={(value) => (customerId = value)} />
				</div>

				<div class="flex flex-col gap-2">
					<div class="text-sm font-medium">{irisT("Short description *", $irisLocale)}</div>
					<Input class="text-sm" autocomplete="off" bind:value={shortDescription} />
				</div>

				{#if error}
					<div
						class="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive sm:col-span-2"
					>
						{error}
					</div>
				{/if}

				<div class="mb-6 mt-2 flex justify-end sm:col-span-2">
					<Button type="submit">{irisT("Create", $irisLocale)}</Button>
				</div>
			</form>
		</div>
	</Dialog.Content>
</Dialog.Root>
