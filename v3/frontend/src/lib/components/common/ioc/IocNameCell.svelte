<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	export let href: string;
	export let id: number;
	export let value: string;
</script>

<a {href} class="block min-w-0 hover:opacity-80">
	<span class="block text-xs text-muted-foreground">{irisT("IOC #", $irisLocale)}{id}</span>
	<!-- `--primary` is theme-aware (see app.css); no dark: override needed. -->
	<span class="block truncate font-mono font-semibold text-primary" title={value}>
		{value}
	</span>
</a>
