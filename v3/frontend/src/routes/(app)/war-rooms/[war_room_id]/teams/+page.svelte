<!--
  War-room teams. Teams are @-mention targets scoped to the war room —
  every war-room member can see and @ any team, but only users added to
  a team receive notifications when it is mentioned.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { Plus, Trash2, Search, Users } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import {
		Dialog,
		DialogContent,
		DialogDescription,
		DialogFooter,
		DialogHeader,
		DialogTitle
	} from '$lib/components/ui/dialog';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { toast } from '$lib/components/ui/toast';
	import { WarRoomTeamsService, type WarRoomTeam } from '$lib/services/war-room-teams.service';
	import { WarRoomsService, type WarRoomMember } from '$lib/services/war-rooms.service';
	import { UsersService, type MentionableUser } from '$lib/services/users.service';

	const warRoomId = $derived(Number(page.params.war_room_id));

	let teams = $state<WarRoomTeam[]>([]);
	let members = $state<WarRoomMember[]>([]);
	let allUsers = $state<MentionableUser[]>([]);
	let loading = $state(true);

	// Create-team dialog
	let createOpen = $state(false);
	let creating = $state(false);
	let newName = $state('');
	let newDescription = $state('');
	let newColor = $state<string>('#3b82f6');

	// Add-member dialog
	let addMemberOpen = $state(false);
	let addingMember = $state(false);
	let addTargetTeam = $state<WarRoomTeam | null>(null);
	let memberSearch = $state('');
	let selectedUserId = $state<number | null>(null);

	// Expansion — which team's members are open.
	let expanded = $state<Set<number>>(new Set());

	const load = async () => {
		loading = true;
		const [teamsRes, membersRes, usersRes] = await Promise.all([
			WarRoomTeamsService.list(warRoomId),
			WarRoomsService.listMembers(warRoomId),
			// `/users/mentionable`, not `/manage/users` — the latter is
			// server_administrator-only and would 403 for the non-admins who
			// can otherwise manage war-room teams.
			UsersService.listMentionable()
		]);
		if (teamsRes.ok && Array.isArray(teamsRes.data)) {
			teams = teamsRes.data;
		}
		if (membersRes.ok && Array.isArray(membersRes.data)) {
			members = membersRes.data;
		}
		if (usersRes.ok && usersRes.data && typeof usersRes.data !== 'string') {
			const payload = usersRes.data as { data?: MentionableUser[] };
			allUsers = Array.isArray(payload.data) ? payload.data : [];
		}
		loading = false;
	};

	onMount(() => {
		load();
	});

	const memberById = $derived(new Map(members.map((m) => [m.user_id, m])));

	const toggleExpand = (teamId: number) => {
		const next = new Set(expanded);
		if (next.has(teamId)) next.delete(teamId);
		else next.add(teamId);
		expanded = next;
	};

	const openCreate = () => {
		newName = '';
		newDescription = '';
		newColor = '#3b82f6';
		createOpen = true;
	};

	const submitCreate = async () => {
		if (!newName.trim()) return;
		creating = true;
		const res = await WarRoomTeamsService.create(warRoomId, {
			name: newName.trim(),
			description: newDescription.trim() || null,
			color: newColor || null
		});
		creating = false;
		if (res.ok) {
			toast({ title: irisT("Team created", $irisLocale) });
			createOpen = false;
			load();
		} else {
			toast({ title: irisT("Could not create team", $irisLocale), variant: 'destructive' });
		}
	};

	const removeTeam = async (t: WarRoomTeam) => {
		if (!confirm(`Delete team "${t.name}"?`)) return;
		const res = await WarRoomTeamsService.remove(warRoomId, t.team_id);
		if (res.ok) {
			teams = teams.filter((x) => x.team_id !== t.team_id);
		} else {
			toast({ title: irisT("Could not delete team", $irisLocale), variant: 'destructive' });
		}
	};

	const openAddMember = (t: WarRoomTeam) => {
		addTargetTeam = t;
		memberSearch = '';
		selectedUserId = null;
		addMemberOpen = true;
	};

	// Room-member lookup for the "not a war-room member yet — will be
	// added as responder" hint in the add-member dialog.
	const roomMemberIds = $derived(new Set(members.map((m) => m.user_id)));

	type UserCandidate = {
		user_id: number;
		user_login: string;
		user_name: string;
		is_room_member: boolean;
	};

	const memberCandidates = $derived.by<UserCandidate[]>(() => {
		if (!addTargetTeam) return [];
		const already = new Set(addTargetTeam.member_ids ?? []);
		const needle = memberSearch.trim().toLowerCase();
		return allUsers
			.filter((u) => !already.has(u.user_id))
			.filter((u) => {
				if (!needle) return true;
				return (
					u.user_login.toLowerCase().includes(needle) || u.user_name.toLowerCase().includes(needle)
				);
			})
			.map((u) => ({
				user_id: u.user_id,
				user_login: u.user_login,
				user_name: u.user_name,
				is_room_member: roomMemberIds.has(u.user_id)
			}))
			.slice(0, 40);
	});

	const selectedCandidate = $derived(
		memberCandidates.find((c) => c.user_id === selectedUserId) ?? null
	);

	const submitAddMember = async () => {
		if (!addTargetTeam || selectedUserId == null) return;
		addingMember = true;
		const res = await WarRoomTeamsService.addMember(
			warRoomId,
			addTargetTeam.team_id,
			selectedUserId
		);
		addingMember = false;
		if (res.ok) {
			const autoAdded =
				res.data &&
				typeof res.data !== 'string' &&
				(res.data as { auto_added_room_member?: boolean }).auto_added_room_member;
			if (autoAdded) {
				toast({
					title: irisT("Member added", $irisLocale),
					description: irisT("Also joined the war room as responder.", $irisLocale)
				});
			} else {
				toast({ title: irisT("Member added", $irisLocale) });
			}
			addMemberOpen = false;
			load();
		} else {
			toast({ title: irisT("Could not add member", $irisLocale), variant: 'destructive' });
		}
	};

	const removeMember = async (t: WarRoomTeam, userId: number) => {
		const label = memberById.get(userId)?.user_name ?? `#${userId}`;
		if (!confirm(`Remove ${label} from team "${t.name}"?`)) return;
		const res = await WarRoomTeamsService.removeMember(warRoomId, t.team_id, userId);
		if (res.ok) {
			load();
		} else {
			toast({ title: irisT("Could not remove team member", $irisLocale), variant: 'destructive' });
		}
	};
</script>

<div class="flex h-full w-full flex-col gap-4 overflow-y-auto p-4 sm:p-6">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-lg font-semibold">{irisT("Teams", $irisLocale)}</h2>
			<p class="text-xs text-muted-foreground">
				{irisT("Group members together and @-mention the group in chat, notes, and tasks. Every member of a\n\t\t\t\tmentioned team gets notified.", $irisLocale)}
			</p>
		</div>
		<Button onclick={openCreate}>
			<Plus class="mr-1 h-4 w-4" /> {irisT("New team", $irisLocale)}
		</Button>
	</div>

	{#if loading}
		<div class="flex flex-col gap-2">
			{#each Array(3) as _}
				<Skeleton class="h-14 w-full" />
			{/each}
		</div>
	{:else if teams.length === 0}
		<p class="text-sm text-muted-foreground">
			{irisT("No teams yet. Create one to start grouping people for @-mentions.", $irisLocale)}
		</p>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each teams as t (t.team_id)}
				{@const memberIds = t.member_ids ?? []}
				{@const isOpen = expanded.has(t.team_id)}
				<li class="rounded-md border bg-card/40">
					<div class="flex items-center gap-3 px-3 py-2">
						<span
							class="inline-block h-3 w-3 shrink-0 rounded-full border"
							style={t.color ? `background-color: ${t.color}` : ''}
							aria-hidden="true"
						></span>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<span class="truncate text-sm font-medium">@{t.name}</span>
								<span class="text-2xs text-muted-foreground">
									{memberIds.length} {irisT("member", $irisLocale)}{memberIds.length === 1 ? '' : 's'}
								</span>
							</div>
							{#if t.description}
								<div class="truncate text-xs text-muted-foreground">
									{t.description}
								</div>
							{/if}
						</div>
						<Button variant="ghost" size="sm" onclick={() => toggleExpand(t.team_id)}>
							<Users class="mr-1 h-3.5 w-3.5" />
							{isOpen ? irisT("Hide", $irisLocale) : irisT("Show", $irisLocale)}
						</Button>
						<Button variant="ghost" size="sm" onclick={() => openAddMember(t)}>
							<Plus class="mr-1 h-3.5 w-3.5" /> {irisT("Add", $irisLocale)}
						</Button>
						<Button
							variant="ghost"
							size="icon"
							class="h-7 w-7 text-destructive hover:text-destructive"
							onclick={() => removeTeam(t)}
							aria-label={irisT("Delete team", $irisLocale)}
						>
							<Trash2 class="h-3.5 w-3.5" />
						</Button>
					</div>
					{#if isOpen}
						<div class="border-t px-3 py-2">
							{#if memberIds.length === 0}
								<p class="text-xs text-muted-foreground">
									{irisT("No members. Add someone with the Add button above.", $irisLocale)}
								</p>
							{:else}
								<ul class="flex flex-wrap gap-1.5">
									{#each memberIds as uid (uid)}
										{@const m = memberById.get(uid)}
										<li
											class="flex items-center gap-1.5 rounded-full border bg-background px-2 py-1 text-xs"
										>
											<span class="truncate">
												{m ? m.user_name : `#${uid}`}
											</span>
											<button
												type="button"
												class="text-muted-foreground hover:text-destructive"
												onclick={() => removeMember(t, uid)}
												aria-label={irisT("Remove from team", $irisLocale)}
											>
												<Trash2 class="h-3 w-3" />
											</button>
										</li>
									{/each}
								</ul>
							{/if}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<Dialog bind:open={createOpen}>
	<DialogContent class="sm:max-w-md">
		<DialogHeader>
			<DialogTitle>{irisT("New team", $irisLocale)}</DialogTitle>
			<DialogDescription>
				{irisT("Teams are per-war-room. Their name is what people type after @.", $irisLocale)}
			</DialogDescription>
		</DialogHeader>
		<div class="flex flex-col gap-3 py-2">
			<div>
				<label class="text-xs font-medium text-muted-foreground" for="team-name"> {irisT("Name", $irisLocale)} </label>
				<Input
					id="team-name"
					value={newName}
					oninput={(e) => (newName = (e.target as HTMLInputElement).value)}
					placeholder={irisT("e.g. ir-leads", $irisLocale)}
				/>
			</div>
			<div>
				<label class="text-xs font-medium text-muted-foreground" for="team-description">
					{irisT("Description", $irisLocale)}
				</label>
				<Textarea
					id="team-description"
					value={newDescription}
					oninput={(e) => (newDescription = (e.target as HTMLTextAreaElement).value)}
					placeholder={irisT("Optional — who's in this team, what they own", $irisLocale)}
					rows={2}
				/>
			</div>
			<div>
				<label class="text-xs font-medium text-muted-foreground" for="team-color"> {irisT("Color", $irisLocale)} </label>
				<input
					id="team-color"
					type="color"
					bind:value={newColor}
					class="h-9 w-16 rounded-md border bg-background"
				/>
			</div>
		</div>
		<DialogFooter>
			<Button variant="ghost" onclick={() => (createOpen = false)} disabled={creating}>
				{irisT("Cancel", $irisLocale)}
			</Button>
			<Button onclick={submitCreate} disabled={creating || !newName.trim()}>
				{creating ? irisT("Creating…", $irisLocale) : irisT("Create", $irisLocale)}
			</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>

<Dialog bind:open={addMemberOpen}>
	<DialogContent class="sm:max-w-lg">
		<DialogHeader>
			<DialogTitle>
				{irisT("Add member to @", $irisLocale)}{addTargetTeam?.name ?? ''}
			</DialogTitle>
			<DialogDescription>
				{irisT("Users who aren't already in this war room will be added as", $irisLocale)}
				<span class="font-medium">{irisT("responder", $irisLocale)}</span> {irisT("automatically.", $irisLocale)}
			</DialogDescription>
		</DialogHeader>
		<div class="flex flex-col gap-3 py-2">
			<div class="relative">
				<Search
					class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
				/>
				<Input
					value={memberSearch}
					oninput={(e) => (memberSearch = (e.target as HTMLInputElement).value)}
					placeholder={irisT("Search by login or name", $irisLocale)}
					class="pl-7"
				/>
			</div>
			<div class="max-h-56 overflow-y-auto rounded-md border">
				{#if memberCandidates.length === 0}
					<div class="p-3 text-center text-xs text-muted-foreground">{irisT("No matching users.", $irisLocale)}</div>
				{:else}
					<ul>
						{#each memberCandidates as m (m.user_id)}
							{@const selected = selectedUserId === m.user_id}
							<li>
								<button
									type="button"
									class={[
										'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
										selected ? 'bg-primary/10' : 'hover:bg-muted/50'
									]}
									onclick={() => (selectedUserId = m.user_id)}
								>
									<span class="flex-1 truncate">{m.user_name}</span>
									<span class="text-2xs text-muted-foreground">
										@{m.user_login}
									</span>
									{#if !m.is_room_member}
										<span
											class="shrink-0 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-2xs font-medium text-amber-700 dark:text-amber-300"
											title={irisT("This user is not in the war room yet — adding them will also add them as responder.", $irisLocale)}
										>
											{irisT("Not in war room", $irisLocale)}
										</span>
									{/if}
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
			{#if selectedCandidate && !selectedCandidate.is_room_member}
				<p
					class="rounded-md border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5 text-2xs text-amber-800 dark:text-amber-300"
				>
					{selectedCandidate.user_name} {irisT("isn't a war-room member yet. Adding them to this team will also\n\t\t\t\t\tadd them to the war room as", $irisLocale)}
					<span class="font-medium">{irisT("responder", $irisLocale)}</span>.
				</p>
			{/if}
		</div>
		<DialogFooter>
			<Button variant="ghost" onclick={() => (addMemberOpen = false)} disabled={addingMember}>
				{irisT("Cancel", $irisLocale)}
			</Button>
			<Button onclick={submitAddMember} disabled={addingMember || selectedUserId == null}>
				{addingMember ? irisT("Adding…", $irisLocale) : irisT("Add", $irisLocale)}
			</Button>
		</DialogFooter>
	</DialogContent>
</Dialog>
