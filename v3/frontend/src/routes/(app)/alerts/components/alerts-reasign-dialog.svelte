<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { onMount } from 'svelte';
	import { UsersService, type MentionableUser } from '$lib/services/users.service';
	import type { Alert } from '$lib/types/resources/alert';
	import * as Dialog from '$lib/components/ui/dialog';
	import Button from '$lib/components/ui/button/button.svelte';
	import { Select } from '$lib/components/ui/select';
	import SelectContent from '$lib/components/ui/select/select-content.svelte';
	import SelectItem from '$lib/components/ui/select/select-item.svelte';
	import SelectTrigger from '$lib/components/ui/select/select-trigger.svelte';

	type Props = {
		open: boolean;
		alert: Alert | null;
		ownerId: string;
		onOwnerIdChange: (v: string) => void;
		onConfirm: () => void;
	};

	let { open = $bindable(), alert, ownerId, onOwnerIdChange, onConfirm }: Props = $props();

	let users = $state<MentionableUser[]>([]);

	const DEFAULT_VALUE = 'Select user';

	// `/api/v2/users/mentionable` is auth-gated but not admin-gated, so
	// standard analysts (who can't call `/manage/users`) can still
	// reassign alerts to colleagues.
	const loadReassignUsers = async () => {
		const res = await UsersService.listMentionable();
		const inner = (res?.data as { data?: MentionableUser[] })?.data;
		if (Array.isArray(inner)) {
			users = inner;
		} else if (Array.isArray(res?.data)) {
			users = res.data as unknown as MentionableUser[];
		} else {
			users = [];
		}
	};

	onMount(() => loadReassignUsers());
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-[520px]">
		<Dialog.Header>
			{#if alert}
				<Dialog.Title>{irisT("Reassign Alert #", $irisLocale)}{alert?.alert_id ?? ''}</Dialog.Title>
			{:else}
				<Dialog.Title>{irisT("Reassign Multiple Alerts", $irisLocale)}</Dialog.Title>
			{/if}
		</Dialog.Header>

		<div class="flex flex-col gap-2 py-2">
			<div class="text-sm font-medium">{irisT("New Owner", $irisLocale)}</div>

			<Select value={ownerId} onValueChange={onOwnerIdChange} type="single">
				<SelectTrigger
					>{users.find((user) => Number(user.user_id) === Number(ownerId))?.user_name ??
						DEFAULT_VALUE}</SelectTrigger
				>

				<SelectContent>
					<SelectItem value="">{DEFAULT_VALUE}</SelectItem>

					{#each users as u (u.user_id)}
						<SelectItem value={String(u.user_id)}>
							{u.user_login ?? u.user_name ?? String(u.user_id)}
						</SelectItem>
					{/each}
				</SelectContent>
			</Select>
		</div>

		<Dialog.Footer class="flex gap-2">
			<Button variant="outline" onclick={() => (open = false)}>{irisT("Cancel", $irisLocale)}</Button>
			<Button disabled={ownerId === ''} onclick={onConfirm}>{irisT("Assign", $irisLocale)}</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
