<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { getContext, onMount } from 'svelte';
	import { RefreshCw } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { Case } from '$lib/types/resources/case';
	import { CASES_CTX, type CasesContext } from '$lib/contexts/cases.context.svelte';
	import type { Paginated, RequestResponse } from '$lib/services/api.service';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card/index.js';
	import CasesDataTable from '$lib/components/common/cases-data-table.svelte';

	const cases = getContext<CasesContext | undefined>(CASES_CTX);

	let casesPromise = $state<Promise<RequestResponse<Paginated<Case>>> | null>(null);

	const currentPage = $derived(() => {
		const p = Number(page.url.searchParams.get('page') ?? '1');
		return Number.isFinite(p) && p >= 1 ? p : 1;
	});

	const fetchPage = (p: number) => {
		if (!cases) return;
		casesPromise = cases.listPaginated({ page: p }) as Promise<RequestResponse<Paginated<Case>>>;
	};

	onMount(() => {
		if (!casesPromise && cases) fetchPage(currentPage());
	});

	const updateUrl = (params: { page?: number }) => {
		const url = new URL(page.url);

		if (params.page !== undefined) {
			if (params.page <= 1) url.searchParams.delete('page');
			else url.searchParams.set('page', String(params.page));
		}

		// IMPORTANT: keep the hash (#cases)
		const nextHref = `${url.pathname}${url.search}${url.hash}`;
		const curHref = `${page.url.pathname}${page.url.search}${page.url.hash}`;
		if (nextHref === curHref) return;

		void goto(nextHref, { replaceState: true, keepFocus: true, noScroll: true });
	};

	const onPageChange = (p: number) => {
		fetchPage(p);
		updateUrl({ page: p });
	};
</script>

<Card.Root class="flex flex-col p-4">
	<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
		<Card.Title class="text-lg font-medium">{irisT("Owned Cases", $irisLocale)}</Card.Title>

		{#if cases}
			<Button
				variant="ghost"
				size="icon"
				onclick={() => {
					fetchPage(currentPage());
				}}
			>
				<RefreshCw class="h-4 w-4" />
			</Button>
		{/if}
	</Card.Header>

	<Card.Content class="p-0">
		{#if casesPromise}
			<CasesDataTable
				class="h-full border-0"
				cases={casesPromise}
				page={currentPage()}
				{onPageChange}
			/>
		{/if}
	</Card.Content>
</Card.Root>
