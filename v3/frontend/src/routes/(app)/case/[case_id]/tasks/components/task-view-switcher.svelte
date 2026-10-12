<!--
  Table / cards / board switcher for the case task views.

  Shared because the board is full-width and hides the sidebar that
  normally carries these buttons — without a copy in the board header
  there would be no way back out of it.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { List, Grid, Columns3 } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Tooltip, TooltipProvider, TooltipTrigger } from '$lib/components/ui/tooltip';
	import TooltipContent from '$lib/components/ui/tooltip/tooltip-content.svelte';
	import type { TaskViewMode } from '$lib/contexts/case-tasks.context.svelte';

	type Props = {
		value: TaskViewMode;
		onSelect: (mode: TaskViewMode) => void;
	};

	let { value, onSelect }: Props = $props();

	const modes = [
		{ mode: 'table', Icon: List, label: irisT("Table View", $irisLocale) },
		{ mode: 'cards', Icon: Grid, label: irisT("Cards View", $irisLocale) },
		{ mode: 'board', Icon: Columns3, label: irisT("Board View", $irisLocale) }
	] as const;
</script>

{#each modes as m (m.mode)}
	<TooltipProvider>
		<Tooltip>
			<TooltipTrigger>
				<Button
					size="icon"
					variant={value === m.mode ? 'secondary' : 'ghost'}
					onclick={() => onSelect(m.mode)}
					aria-label={m.label}
				>
					<m.Icon size={16} />
				</Button>
			</TooltipTrigger>
			<TooltipContent align="center" side="bottom">{m.label}</TooltipContent>
		</Tooltip>
	</TooltipProvider>
{/each}
