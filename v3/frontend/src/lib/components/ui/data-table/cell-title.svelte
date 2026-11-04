<script lang="ts">
	import { logger } from '$lib/observability/logger';

	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import * as Tooltip from '$lib/components/ui/tooltip';

	export let params;

	$: title = params?.title ?? '';
	$: redirUrl = params?.redirUrl ?? '';

	// Handle button click for navigation
	function handleClick() {
		if (redirUrl) {
			goto(redirUrl);
		} else {
			logger.error('Invalid element provided:', redirUrl);
		}
	}

	export function refresh(_props: any): boolean {
		return false;
	}
</script>

<div class="flex items-center">
	<Tooltip.Provider>
		<Tooltip.Root delayDuration={300}>
			<Tooltip.Trigger>
				<Button variant="dotted" size="sm" onclick={handleClick}>
					{title}
				</Button>
			</Tooltip.Trigger>
			<Tooltip.Content>{irisT("Click to view details", $irisLocale)}</Tooltip.Content>
		</Tooltip.Root>
	</Tooltip.Provider>
</div>
