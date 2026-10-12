<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();
</script>
<h2 class="my-4 text-lg">{irisT("Rules of engagement", $irisLocale)}</h2>

<p>
	<span class="font-bold">{irisT("If you find a vulnerability", $irisLocale)}</span>{irisT(", contact us before going public as it\n\tmay impact systems already in production.", $irisLocale)}
</p>

<p>
	{irisT("In other words, please respect a responsible disclosure of 30 days. We will patch and then publish\n\tvulnerability. Depending on the finding a CVE might be requested, and will have your name - except\n\tif you dont want to.", $irisLocale)}
</p>

<p>
	{irisT("You can report anything you find at", $irisLocale)} <a href="mailto:contact@dfir-iris.org"
		>{irisT("contact@dfir-iris.org", $irisLocale)}</a
	>.
</p>

<p class="mt-4">
	<span class="font-bold">{irisT("The scope of the security tests", $irisLocale)}</span> {irisT("is limited to the Web Application\n\tIRIS hosted on", $irisLocale)} <a href="https://v200.beta.dfir-iris.org">{irisT("v200.beta.dfir-iris.org", $irisLocale)}</a>.
</p>

<p class="mb-4 text-red-500">
	{irisT("Subdomains, SSH, scanning of the IP, BF, and other flavors are", $irisLocale)} <span class="font-bold"
		>{irisT("out of scope", $irisLocale)}</span
	>.
</p>

<p>{irisT("We are mostly interested in the following:", $irisLocale)}</p>

<ul class="list-disc pl-6">
	<li>
		<span class="font-bold">{irisT("authentication bypass", $irisLocale)}</span>{irisT(": achieve any action requiring an\n\t\tauthentication without being authenticated.", $irisLocale)}
		<span class="text-red-500">{irisT("Brute-force is not what we are looking for", $irisLocale)}</span>
	</li>

	<li>
		<span class="font-bold">{irisT("privilage excalations within the application", $irisLocale)}</span>{irisT(": from a standard\n\t\tuser (", $irisLocale)}<span class="font-red-400 font-mono">{irisT("user_std_XX", $irisLocale)}</span>{irisT(") to administrative rights (", $irisLocale)}<span
			class="font-red-400 font-mono">{irisT("adm_XX", $irisLocale)}</span
		>{irisT(") on IRIS", $irisLocale)}
	</li>

	<li>
		<span class="font-bold">{irisT("privilage escalations on the host server", $irisLocale)}</span>{irisT(": from a standard user (", $irisLocale)}<span
			class="font-red-400 font-mono">{irisT("user_std_XX", $irisLocale)}</span
		>{irisT(") to code execution on the server", $irisLocale)}
	</li>

	<li>
		<span class="font-bold">{irisT("data leakage", $irisLocale)}</span>{irisT(": from a standard user (", $irisLocale)}<span
			class="font-red-400 font-mono">{irisT("user_std_XX", $irisLocale)}</span
		>{irisT(") read data of non-accessible cases (titled", $irisLocale)}
		<span class="font-mono text-red-500">{irisT("Restricted Case XXX", $irisLocale)}</span>)
	</li>
</ul>

<h2 class="my-4 text-lg">{irisT("Important Remarks", $irisLocale)}</h2>

<ul class="list-disc pl-6">
	<li>
		{irisT("If you can, use a local intance of IRIS instead of this one. It only takes a few minuts to get\n\t\tit on docker.", $irisLocale)}
	</li>
	<li>
		{irisT("The administrators account can publish stored XSS on the platform via Custom Attributes. This is\n\t\tan operational requirement and not recognized as a vulnerability.", $irisLocale)}
	</li>
	<li>
		<span class="font-bold">{irisT("Try not to be destructive", $irisLocale)}</span>{irisT(". If you manage to run code on the host\n\t\tserver, do not try to go further.", $irisLocale)}
	</li>
</ul>

<h2 class="my-4 text-lg">{irisT("Restrictions", $irisLocale)}</h2>

<p>{irisT("To keep this instance alive, there are some restrictions put in place.", $irisLocale)}</p>

<ul class="list-disc pl-6">
	<li>
		{irisT("The", $irisLocale)} <span class="font-mono text-red-500">{irisT("administrator", $irisLocale)}</span> {irisT("account cannot be updated nor deleted.", $irisLocale)}
	</li>
	<li>{irisT("The accounts available on this page cannot be updated nore deleted.", $irisLocale)}</li>
	<li>{irisT("File upload in datastore is limited to 200KB per file.", $irisLocale)}</li>
</ul>

<h2 class="my-4 text-lg">{irisT("Resources", $irisLocale)}</h2>

<p>
	{irisT("You can read more about IRIS on the", $irisLocale)} <a href="https://docs.dfir-iris.org/latest/"
		>{irisT("official documentation website", $irisLocale)}</a
	>.
</p>
<p>
	{irisT("IRIS is an open source app, so you can directly access the code on", $irisLocale)} <a href="htts://github.com"
		>{irisT("GitHub", $irisLocale)}</a
	>.
</p>
