<!--
  Colour picker of the asset-flag palette (round swatches, one radio
  each). Shared by the asset flags settings and the war-room tracker steps.
-->
<script lang="ts">
	import { GRAPH_RELATION_COLORS } from '$lib/types/resources/case-graph';
	import { paletteHex } from '$lib/components/common/CytoscapeGraph/palette';

	type Props = {
		value: string;
		disabled?: boolean;
		/** Id of the element labelling the group. */
		labelledby?: string;
	};

	let { value = $bindable(), disabled = false, labelledby }: Props = $props();
</script>

<div class="flex flex-wrap gap-1.5" role="radiogroup" aria-labelledby={labelledby}>
	{#each GRAPH_RELATION_COLORS as color (color)}
		<button
			type="button"
			role="radio"
			aria-checked={value === color}
			aria-label={color}
			title={color}
			style:background-color={paletteHex(color, false)}
			{disabled}
			onclick={() => (value = color)}
			class="h-6 w-6 rounded-full {value === color
				? 'ring-2 ring-ring ring-offset-2 ring-offset-background'
				: ''}"
		></button>
	{/each}
</div>
