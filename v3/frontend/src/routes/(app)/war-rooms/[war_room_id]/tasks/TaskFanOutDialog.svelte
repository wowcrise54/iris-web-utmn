<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '$lib/components/ui/dialog';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { ApiService } from '$lib/services/api.service';
	import type { TaskStatus } from '$lib/types/resources/task';

	type Destination = {
		case_id: number;
		case_name: string | null;
		case_task_id: number | null;
		status_name: string | null;
		can_create: boolean;
	};

	let { open = $bindable(false), warRoomId, taskId, title, statuses }: {
		open: boolean;
		warRoomId: number;
		taskId: number;
		title: string;
		statuses: TaskStatus[];
	} = $props();
	const locale = useLocale();
	const path = $derived(`/api/v2/war-rooms/${warRoomId}/tasks/${taskId}/fan-out`);
	let destinations = $state<Destination[]>([]);
	let selected = $state<number[]>([]);
	let assignOwner = $state(true);
	let statusId = $state<number | null>(null);
	let pending = $state(false);
	let error = $state('');

	async function load(url: string) {
		pending = true;
		error = '';
		const response = await ApiService.get<Destination[]>(url);
		if (!open || url !== path) return;
		if (response.ok && Array.isArray(response.data)) destinations = response.data;
		else error = 'Could not load linked case tasks.';
		pending = false;
	}

	$effect(() => {
		if (!open) return;
		destinations = [];
		selected = [];
		statusId = null;
		assignOwner = true;
		void load(path);
	});

	async function distribute() {
		const url = path;
		pending = true;
		error = '';
		const response = await ApiService.post(url, {
			case_ids: selected, status_id: statusId, assign_to_case_owner: assignOwner
		});
		if (!open || url !== path) return;
		if (response.ok) {
			selected = [];
			await load(url);
		} else {
			error = 'Could not distribute the task.';
			pending = false;
		}
	}
</script>

<Dialog bind:open>
	<DialogContent class="max-w-lg">
		<DialogHeader>
			<DialogTitle>{irisT('Linked case tasks', $locale)}</DialogTitle>
		</DialogHeader>
		<p class="break-words text-sm font-medium">{title}</p>
		{#if error}
			<p role="alert" class="text-sm text-destructive">{irisT(error, $locale)}</p>
		{:else if pending && !destinations.length}
			<p role="status" class="text-sm text-muted-foreground">{irisT('Loading', $locale)}</p>
		{:else if !destinations.length}
			<p class="text-sm text-muted-foreground">{irisT('No accessible linked cases', $locale)}</p>
		{/if}
		<ul class="grid max-h-64 gap-2 overflow-auto">
			{#each destinations as target (target.case_id)}
				{@const label = target.case_name || `#${target.case_id}`}
				<li class="flex items-center justify-between gap-2 rounded border p-2 text-sm">
					{#if target.case_task_id !== null}
						<a class="text-primary underline"
							href={`/case/${target.case_id}/tasks/${target.case_task_id}`}>
							{label} · #{target.case_task_id}
						</a>
						{#if target.status_name}<span>{irisT(target.status_name, $locale)}</span>{/if}
					{:else if target.can_create}
						<label class="flex items-center gap-2">
							<input type="checkbox" value={target.case_id} bind:group={selected}
								disabled={pending || (selected.length >= 50 && !selected.includes(target.case_id))} />
							{label}
						</label>
					{:else}
						<span>{label}</span>
						<span class="text-muted-foreground">{irisT('Read only', $locale)}</span>
					{/if}
				</li>
			{/each}
		</ul>
		{#if destinations.some((target) => target.can_create && target.case_task_id === null)}
			<p class="text-sm text-muted-foreground">
				{irisT('The title, description and tags will be copied to the selected cases.', $locale)}
			</p>
			<label class="flex items-center justify-between gap-2 text-sm">
				{irisT('Initial task status', $locale)}
				<select class="rounded border bg-background p-1.5" bind:value={statusId} disabled={pending}>
					<option value={null}>{irisT('Default status', $locale)}</option>
					{#each statuses as status (status.id)}
						<option value={status.id}>{irisT(status.status_name, $locale)}</option>
					{/each}
				</select>
			</label>
			<label class="flex items-center gap-2 text-sm">
				<input type="checkbox" bind:checked={assignOwner} disabled={pending} />
				{irisT('Assign to the case owner when eligible', $locale)}
			</label>
		{/if}
		<DialogFooter>
			<Button variant="outline" onclick={() => (open = false)}>{irisT('Close', $locale)}</Button>
			{#if selected.length}
				<Button disabled={pending} onclick={() => void distribute()}>{irisT('Distribute task', $locale)}</Button>
			{/if}
		</DialogFooter>
	</DialogContent>
</Dialog>
