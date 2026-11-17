<script lang="ts">
	import { logger } from '$lib/observability/logger';

	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { formatDateTime, timeZoneLabel } from '$lib/utils/time-formatter';
	import { page } from '$app/state';
	import { current_user, username } from '$lib/stores/auth.store';
	import { mode, toggleMode } from 'mode-watcher';
	import { BellIcon, LogOutIcon, MoonIcon, SlidersHorizontalIcon, SunIcon } from 'lucide-svelte';
	import { AuthService } from '$lib/services/auth.service';
	import UserAvatar from '$lib/components/common/UserAvatar.svelte';
	import MenuItem from './MenuItem.svelte';
	import SubMenu from './SubMenu.svelte';

	type Props = {
		collapsed: boolean;
	};

	let { collapsed }: Props = $props();

	const pathname = $derived(page.url.pathname);
	const _hash = $derived(page.url.hash);

	// Auth is loaded from the root `+layout.svelte` effect; a second
	// `loadAuth` call here used to race the first one, sometimes wiping
	// the just-populated user state on token-rotation 401s. Read the
	// auth-store directly instead.
	const logout = () => {
		logger.debug('Logging out...');

		AuthService.logout();
	};
</script>

<SubMenu {collapsed}>
	<svelte:fragment slot="trigger">
		<UserAvatar
			userId={$current_user?.user_id ?? $current_user?.id}
			name={$username === 'Loading...' ? null : $username}
			size="size-10"
		/>

		<div
			class={`flex w-full items-center justify-between overflow-hidden transition-all ${collapsed ? 'ml-0 max-w-0' : 'ml-2 max-w-96'}`}
		>
			<div class="flex w-full flex-col items-start justify-center">
				<span class="text-[13px] font-semibold text-foreground">{$username}</span>
				<span class="whitespace-nowrap text-2xs font-normal text-muted-foreground"
					>{formatDateTime(Date.now())} {timeZoneLabel()}</span
				>
			</div>
		</div>
	</svelte:fragment>

	<svelte:fragment slot="menu">
		<MenuItem
			{collapsed}
			label={irisT("My profile", $irisLocale)}
			icon={SlidersHorizontalIcon}
			href="/profile"
			liClass="mt-4"
			active={pathname === '/profile'}
		/>

		<MenuItem
			{collapsed}
			label={irisT("Notifications", $irisLocale)}
			icon={BellIcon}
			href="/profile/notifications"
			active={pathname === '/profile/notifications'}
		/>

		{#if $mode === 'light'}
			<MenuItem {collapsed} label={irisT("Light mode", $irisLocale)} icon={SunIcon} onClick={() => toggleMode()} />
		{:else}
			<MenuItem {collapsed} label={irisT("Dark mode", $irisLocale)} icon={MoonIcon} onClick={() => toggleMode()} />
		{/if}

		<MenuItem {collapsed} label={irisT("Log Out", $irisLocale)} icon={LogOutIcon} onClick={() => logout()} />
	</svelte:fragment>
</SubMenu>
