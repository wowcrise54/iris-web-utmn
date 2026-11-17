<script lang="ts">
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { ApiService } from '$lib/services/api.service';
	import { formatDateTime } from '$lib/utils/time-formatter';

	type Status = 'proposed' | 'approved' | 'rejected' | 'implemented';
	type Action = Exclude<Status, 'proposed'>;
	type Entry = { status: Status; actor_id: number; actor_name: string; at: string; comment: string };
	type Decision = { id: number; title: string; rationale: string; status: Status; history: Entry[] };
	type Journal = { items: Decision[]; next_before: number | null; can_write: boolean };

	const locale = useLocale();
	const path = $derived(`/api/v2/war-rooms/${page.params.war_room_id}/decisions`);
	const statuses: Record<Status, string> = {
		proposed: 'Proposed', approved: 'Approved', rejected: 'Rejected', implemented: 'Implemented'
	};
	const actions: Record<Action, string> = {
		approved: 'Approve', rejected: 'Reject decision', implemented: 'Mark implemented'
	};
	let decisions = $state<Decision[]>([]);
	let nextBefore = $state<number | null>(null);
	let canWrite = $state(false);
	let pending = $state(false);
	let error = $state('');
	let creating = $state(false);
	let title = $state('');
	let rationale = $state('');
	let action = $state<{ id: number; status: Action } | null>(null);
	let comment = $state('');

	async function load(url: string, before: number | null = null) {
		pending = true;
		error = '';
		const res = await ApiService.get<Journal>(ApiService.withQuery(url, { before }));
		if (url !== path) return;
		if (res.ok && res.data && typeof res.data === 'object') {
			decisions = before === null ? res.data.items : [...decisions, ...res.data.items];
			nextBefore = res.data.next_before;
			canWrite = res.data.can_write;
			if (before === null) action = null;
		} else {
			error = 'Could not load the decision journal.';
		}
		pending = false;
	}

	$effect(() => {
		const url = path;
		decisions = [];
		nextBefore = null;
		canWrite = false;
		creating = false;
		title = rationale = comment = '';
		action = null;
		void load(url);
	});

	async function submitDecision() {
		const url = path;
		pending = true;
		error = '';
		const res = await ApiService.post<Decision>(url, { title, rationale });
		if (url !== path) return;
		if (res.ok && res.data && typeof res.data === 'object') {
			decisions = [res.data, ...decisions];
			creating = false;
			title = rationale = '';
		} else {
			error = 'Could not save the decision.';
		}
		pending = false;
	}

	function chooseAction(id: number, status: Action) {
		comment = '';
		action = { id, status };
	}

	async function submitStatus(id: number, status: Action) {
		const url = path;
		pending = true;
		error = '';
		const res = await ApiService.post<Decision>(`${url}/${id}/status`, { status, comment });
		if (url !== path) return;
		if (res.ok && res.data && typeof res.data === 'object') {
			const saved = res.data;
			decisions = decisions.map((decision) => decision.id === id ? saved : decision);
			action = null;
			comment = '';
		} else {
			error = res.status === 409
				? 'This action is unavailable for the current decision status.'
				: 'Could not save the decision.';
		}
		pending = false;
	}
</script>

<section class="h-full overflow-y-auto p-4">
	<header class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<h1 class="text-xl font-semibold">{irisT('Decision journal', $locale)}</h1>
		<div class="flex gap-2">
			<Button variant="outline" disabled={pending} onclick={() => void load(path)}>
				{irisT('Refresh', $locale)}
			</Button>
			{#if canWrite}
				<Button disabled={pending} onclick={() => (creating = !creating)}>
					{irisT('Propose decision', $locale)}
				</Button>
			{/if}
		</div>
	</header>

	{#if error}
		<p role="alert" class="mb-3 text-sm text-destructive">{irisT(error, $locale)}</p>
	{/if}
	{#if canWrite && creating}
		<form class="mb-4 grid max-w-3xl gap-3 rounded-md border p-4" onsubmit={(event) => {
			event.preventDefault();
			void submitDecision();
		}}>
			<label class="grid gap-1">
				{irisT('Title', $locale)}
				<Input required maxlength={256} bind:value={title} disabled={pending} />
			</label>
			<label class="grid gap-1">
				{irisT('Decision rationale', $locale)}
				<textarea class="min-h-24 rounded-md border bg-background p-2"
					required maxlength={20000} bind:value={rationale} disabled={pending}></textarea>
			</label>
			<Button class="justify-self-start" type="submit" disabled={pending}>
				{irisT('Propose decision', $locale)}
			</Button>
		</form>
	{/if}
	{#if !pending && !error && !decisions.length}
		<p class="text-sm text-muted-foreground">{irisT('No decisions recorded', $locale)}</p>
	{/if}

	<div class="grid max-w-4xl gap-3">
		{#each decisions as decision (decision.id)}
			<article class="grid gap-3 rounded-md border p-4">
				<div class="flex flex-wrap items-start justify-between gap-2">
					<h2 class="min-w-0 break-words font-semibold">{decision.title}</h2>
					<span class="rounded border px-2 py-0.5 text-sm">{irisT(statuses[decision.status], $locale)}</span>
				</div>
				<p class="whitespace-pre-wrap break-words text-sm">{decision.rationale}</p>
				<ol class="space-y-2 border-s ps-3 text-sm">
					{#each decision.history as entry}
						<li>
							<span class="font-medium">{irisT(statuses[entry.status], $locale)}</span>
							<span class="text-muted-foreground"> · {entry.actor_name || `#${entry.actor_id}`} ·
								{formatDateTime(entry.at)}</span>
							{#if entry.comment}
								<p class="whitespace-pre-wrap break-words">{entry.comment}</p>
							{/if}
						</li>
					{/each}
				</ol>
				{#if canWrite && decision.status === 'proposed'}
					<div class="flex flex-wrap gap-2">
						<Button variant="outline" disabled={pending} onclick={() => chooseAction(decision.id, 'approved')}>
							{irisT(actions.approved, $locale)}
						</Button>
						<Button variant="outline" disabled={pending} onclick={() => chooseAction(decision.id, 'rejected')}>
							{irisT(actions.rejected, $locale)}
						</Button>
					</div>
				{:else if canWrite && decision.status === 'approved'}
					<Button class="justify-self-start" variant="outline" disabled={pending}
						onclick={() => chooseAction(decision.id, 'implemented')}>{irisT(actions.implemented, $locale)}</Button>
				{/if}
				{#if canWrite && action?.id === decision.id}
					{@const status = action.status}
					<form class="grid gap-2 border-t pt-3" onsubmit={(event) => {
						event.preventDefault();
						void submitStatus(decision.id, status);
					}}>
						<label class="grid gap-1">
							{irisT('Comment', $locale)}
							<textarea class="rounded-md border bg-background p-2"
								maxlength={4000} bind:value={comment} disabled={pending}></textarea>
						</label>
						<div class="flex gap-2">
							<Button type="submit" disabled={pending}>{irisT(actions[status], $locale)}</Button>
							<Button type="button" variant="ghost" disabled={pending} onclick={() => (action = null)}>
								{irisT('Cancel', $locale)}
							</Button>
						</div>
					</form>
				{/if}
			</article>
		{/each}
		{#if nextBefore !== null}
			{@const before = nextBefore}
			<Button class="justify-self-start" variant="outline" disabled={pending} onclick={() => void load(path, before)}>
				{irisT('Load more', $locale)}
			</Button>
		{/if}
	</div>
</section>
