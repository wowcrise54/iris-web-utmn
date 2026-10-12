<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';

	// War rooms land on the chat tab by default — that's the IR commander's
	// primary surface and where the action happens. Other tabs are
	// secondary views.
	onMount(() => {
		goto(`/war-rooms/${page.params.war_room_id}/chat`, { replaceState: true });
	});
</script>

<div class="flex h-full items-center justify-center text-sm text-muted-foreground">{irisT("Loading…", $irisLocale)}</div>
