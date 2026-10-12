<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();
</script>
<h2 class="my-4 text-lg">{irisT("Disclaimer", $irisLocale)}</h2>

<p>
	{irisT("DFIR-IRIS is a non-profit organization. It is not responsible for any damage caused by the use of\n\tthis site and any material contained in it, or from any action or decision taken as a result of\n\tusing this site.", $irisLocale)}
</p>

<p>{irisT("It is not responsible for the content of any external sites linked to this site.", $irisLocale)}</p>

<p>
	{irisT("By using this site, you acknowledge that content posted on this site is public and DFIR-IRIS\n\tcannot guarantee the security of any information disclose on it; you make such disclosures at your\n\town risk.", $irisLocale)}
</p>

<h2 class="my-4 text-lg">{irisT("Privacy", $irisLocale)}</h2>

<p>
	{irisT("This instance is shared and we cannot guarantee the privacy of data you might upload on it. We are\n\tnot responsible for any data loss or data leak.", $irisLocale)}
</p>

<p>
	{irisT("To better understand the use of this instance, DFIR-IRIS uses a privacy-friendly cookie-less\n\tnalytics. DFIR-IRIS does not collect any personal data. DFIR-IRIS does not use any third-party\n\tanalytics and uses a self-hosted", $irisLocale)} <a href="https://plausible.io/">{irisT("Plausible", $irisLocale)}</a> {irisT("instance.", $irisLocale)}
</p>
