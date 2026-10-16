<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import Button from '$lib/components/ui/button/button.svelte';
	import Card from '$lib/components/ui/card/card.svelte';
	import { USER_CTX, type UserCtx } from '$lib/contexts/user-context.context.svelte';
	import Disclaimer from './Disclaimer.svelte';
	import RulesOfEngagement from './RulesOfEngagement.svelte';
	import Accounts from './Accounts.svelte';

	let expandedSection = $state<'rules' | 'disclaimer' | 'accounts' | null>(null);

	const toggleRules = () => (expandedSection = expandedSection === 'rules' ? null : 'rules');
	const toggleDisclaimer = () =>
		(expandedSection = expandedSection === 'disclaimer' ? null : 'disclaimer');
	const toggleAccounts = () =>
		(expandedSection = expandedSection === 'accounts' ? null : 'accounts');

	// The welcome page only makes sense on the demo instance — it
	// surfaces the public rules-of-engagement / disclaimer for shared
	// hosts. On a private deployment a user who navigates here
	// directly gets bounced to Home rather than seeing a page that
	// doesn't apply to them.
	const userCtx = getContext<UserCtx>(USER_CTX);
	$effect(() => {
		if (userCtx.ready && !userCtx.ctx?.demo_mode) {
			void goto('/', { replaceState: true });
		}
	});
</script>

<svelte:head>
	<title>{irisT("Welcome", $irisLocale)}</title>
</svelte:head>

<div class="mx-auto my-4 w-full max-w-6xl">
	<Card>
		<div class="flex flex-col px-24 py-4">
			<img src="/img/logo/logo-full-blue.png" alt={irisT("IRIS Logo", $irisLocale)} class="mx-auto w-96" />

			<h2 class="my-6 text-lg">{irisT("Kindly read the following carefully", $irisLocale)}</h2>

			<ul class="my-2 list-disc pl-6">
				<li>{irisT("Do not upload any illegal or confidential materials", $irisLocale)}</li>
				<li>{irisT("Do not download and open files from other users blindly", $irisLocale)}</li>
				<li>
					{irisT("Respect a", $irisLocale)} <a
						href="https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html#responsible-or-coordinated-disclosure"
						>{irisT("responsible disclosure", $irisLocale)}</a
					> {irisT("of 30 days if you find a vulnerability", $irisLocale)}
				</li>
			</ul>

			<p class="my-6 font-bold">
				{irisT("Not sure what IRIS is about? You'll find out more info on the", $irisLocale)} <a
					href="https://www.dfir-iris.org/">{irisT("main website", $irisLocale)}</a
				>
			</p>

			<p>{irisT("IRIS is not optimized to be used on phones. We recommend accessint it from a computer.", $irisLocale)}</p>
			<p>{irisT("If you notice anything suspicious or have any question, please contact us.", $irisLocale)}</p>

			<p class="my-6 italic">
				{irisT("By accessing this instance you confirm you read, understand and agree with all the\n\t\t\t\tinformation on this page.", $irisLocale)}
			</p>

			<div class="mx-auto my-6 flex gap-4">
				<Button onclick={toggleRules}>{irisT("Rules of engagement", $irisLocale)}</Button>
				<Button onclick={toggleDisclaimer}>{irisT("Disclaimer", $irisLocale)}</Button>
				<Button onclick={toggleAccounts}>{irisT("Accounts", $irisLocale)}</Button>
			</div>

			{#if expandedSection !== null}
				<div class="mt-2 border-t pt-4">
					{#if expandedSection === 'rules'}
						<RulesOfEngagement />
					{/if}

					{#if expandedSection === 'disclaimer'}
						<Disclaimer />
					{/if}

					{#if expandedSection === 'accounts'}
						<Accounts />
					{/if}
				</div>
			{/if}
		</div>
	</Card>
</div>
