<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	type Props = {
		sampleCsv: string;
		onCsvChange: (csvText: string) => void;
	};

	let { sampleCsv, onCsvChange }: Props = $props();

	let csvFile = $state<File | null>(null);
	let csvText = $state('');

	const readCsvFile = async (file: File) => {
		csvFile = file;
		csvText = await file.text();

		onCsvChange(csvText);
	};
</script>

<div class="space-y-5">
	<div class="space-y-2">
		<div class="text-sm font-medium">{irisT("Expected CSV file format", $irisLocale)}</div>

		<textarea
			class="h-16 w-full resize-none rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs text-muted-foreground"
			readonly
			value={irisT("asset_name,asset_type_name,asset_description,asset_ip,asset_domain,asset_tags (separated with \"|\")", $irisLocale)}
		></textarea>
	</div>

	<div class="space-y-2">
		<div class="text-sm font-medium">{irisT("CSV file format example", $irisLocale)}</div>

		<textarea
			class="h-28 w-full resize-none rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs text-muted-foreground"
			readonly
			value={sampleCsv}
		></textarea>
	</div>

	<div class="space-y-2">
		<div class="text-sm font-medium">{irisT("Choose CSV file to import", $irisLocale)}</div>

		<input
			type="file"
			accept="text/csv,.csv"
			class="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
			onchange={(event) => {
				const file = (event.target as HTMLInputElement).files?.[0];

				if (file) {
					readCsvFile(file);
				}
			}}
		/>

		{#if csvFile}
			<p class="text-xs text-muted-foreground">
				{irisT("Loaded", $irisLocale)} {csvFile.name} ({csvText.length} {irisT("bytes)", $irisLocale)}
			</p>
		{/if}
	</div>
</div>
