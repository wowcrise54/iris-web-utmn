<!--
  Server Settings page.

  Single-form layout (no master/detail — there's only one server) with
  sections for the legacy `manage_srv_settings.html` groups:
    • Versions     — read-only strip at the top.
    • Proxy        — HTTP / HTTPS module proxies.
    • Post-init    — whether the boot routine re-registers defaults.
    • Password policy.
    • Auth         — enforce MFA.
    • Confirmation — prompt before delete.
    • Database backup — POST trigger + log viewer.

  Save sends only the fields the admin actually changed (`dirty`
  tracking + `Object.entries` diff at submit time) so toggling one
  switch doesn't reset every other value in concurrent admin sessions.
  Mirrors the legacy /manage/settings page 1:1.
-->
<script lang="ts">
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	const irisLocale = useLocale();

	import { getContext } from 'svelte';
	import {
		BugIcon,
		DatabaseIcon,
		InboxIcon,
		KeyRoundIcon,
		MailIcon,
		PowerIcon,
		RefreshCwIcon,
		SaveIcon,
		SendIcon,
		ServerCogIcon,
		ShieldAlertIcon,
		WifiIcon
	} from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Switch } from '$lib/components/ui/switch';
	import { toast } from '$lib/components/ui/toast';
	import ConfirmationDialog from '$lib/components/ui/dialog/ConfirmationDialog.svelte';
	import {
		ServerSettingsService,
		type ServerSettings,
		type ServerSettingsResponse,
		type ServerSettingsUpdateBody
	} from '$lib/services/server-settings.service';
	import { USER_CTX, type UserCtx } from '$lib/contexts/user-context.context.svelte';
	import {
		demoHidesServerSettings,
		demoLocksCredentials
	} from '$lib/services/user-context.service';

	const userCtx = getContext<UserCtx>(USER_CTX);
	// A demo instance keeps this whole surface for its owner — the GET
	// below 403s for anyone else, so show the reason instead of an
	// empty page with a failure toast.
	const restricted = $derived(demoHidesServerSettings(userCtx.ctx));
	// MFA is off wholesale in demo mode (shared accounts, a second
	// factor bound to one visitor locks out the rest), so the toggle
	// would be a lie even for the owner.
	const mfaLocked = $derived(demoLocksCredentials(userCtx.ctx));

	let payload = $state<ServerSettingsResponse | null>(null);
	let loading = $state(false);
	let saveError = $state<string | null>(null);
	let saving = $state(false);

	// Working copy of the settings the form mutates. Diffed against
	// `payload.settings` on save so only changed fields hit the wire.
	let form = $state<Partial<ServerSettings>>({});

	// Backup state
	let backupBusy = $state(false);
	let backupLogs = $state<string[] | null>(null);
	let backupError = $state<string | null>(null);

	// Mail test-send state. `testMailBusy` guards double-submits;
	// the result string is either a green success line or a red
	// error line rendered inline under the Send button.
	let testMailRecipient = $state('');
	let testMailBusy = $state(false);
	let testMailResult = $state<{ ok: boolean; text: string } | null>(null);

	// Shared confirmation dialog (used for the destructive-ish Run
	// backup button — it's long-running and writes to disk so a
	// confirm prompt is worth the friction).
	let confirmOpen = $state(false);
	let confirmTitle = $state('');
	let confirmMessage = $state('');
	let confirmAction = $state<() => Promise<void> | void>(() => {});

	const showError = (msg: string, fallback = 'Operation failed') =>
		toast({ title: msg || fallback, variant: 'destructive' });
	const showSuccess = (msg: string) => toast({ title: msg, variant: 'success' });

	const load = async () => {
		loading = true;
		try {
			const res = await ServerSettingsService.get();
			if (res.ok && res.data && typeof res.data !== 'string') {
				payload = res.data as ServerSettingsResponse;
				// Snapshot the row into the editable form so each
				// individual <Switch>/<Input> binds to a local copy
				// rather than the server's row directly.
				form = { ...payload.settings };
			} else {
				showError(res.error?.message ?? 'Failed to load server settings');
			}
		} finally {
			loading = false;
		}
	};

	// Deliberately not `onMount(load)`: `restricted` only becomes
	// meaningful once /me/context has landed, and a demo visitor who
	// isn't the instance owner must not fire a GET that can only 403.
	let loadRequested = false;
	$effect(() => {
		if (!userCtx.ready || loadRequested) return;
		loadRequested = true;
		if (restricted) return;
		void load();
	});

	const fieldChanged = <K extends keyof ServerSettings>(key: K): boolean => {
		if (payload == null) return false;
		const original = (payload.settings as ServerSettings)[key];
		const current = (form as Partial<ServerSettings>)[key];
		// Compare with `!==` after normalising null/undefined since
		// the schema marshals empty strings as null on the wire.
		return (original ?? null) !== (current ?? null);
	};

	// Union of server-echoed keys AND locally-typed keys. Load-only
	// secrets (mail_smtp_password, mail_imap_password,
	// error_reporting_backend_dsn, chatbot_api_key) are omitted from
	// the GET response, so iterating `payload.settings` alone would
	// silently drop any newly-typed value in those fields — you'd hit
	// "Save" and the PUT would omit the field, leaving the ciphertext
	// unchanged.
	const changedKeys = (): Array<keyof ServerSettings> => {
		if (payload == null) return [];
		const settings = payload.settings as ServerSettings;
		const keys = new Set<keyof ServerSettings>();
		for (const k of Object.keys(settings) as Array<keyof ServerSettings>) keys.add(k);
		for (const k of Object.keys(form) as Array<keyof ServerSettings>) keys.add(k);
		return [...keys];
	};

	const isDirty = $derived.by<boolean>(() => {
		if (payload == null) return false;
		return changedKeys().some((k) => fieldChanged(k));
	});

	const buildPatch = (): ServerSettingsUpdateBody => {
		if (payload == null) return {};
		const patch: ServerSettingsUpdateBody = {};
		for (const key of changedKeys()) {
			if (fieldChanged(key)) {
				(patch as Record<string, unknown>)[key] = (form as Record<string, unknown>)[key];
			}
		}
		return patch;
	};

	const save = async () => {
		const patch = buildPatch();
		if (Object.keys(patch).length === 0) return;
		saving = true;
		saveError = null;
		try {
			const res = await ServerSettingsService.update(patch);
			if (res.ok && res.data && typeof res.data !== 'string') {
				// Backend echoes the full row — update our snapshot
				// so `isDirty` flips back to false.
				if (payload != null) {
					payload = {
						...payload,
						settings: res.data as ServerSettings
					};
				}
				form = { ...(res.data as ServerSettings) };
				showSuccess('Server settings updated');
			} else {
				const data = res.data as { message?: string; data?: unknown } | null;
				saveError = data?.message ?? res.error?.message ?? 'Save failed';
			}
		} catch (e) {
			saveError = (e as Error).message;
		} finally {
			saving = false;
		}
	};

	const discard = () => {
		if (payload == null) return;
		form = { ...payload.settings };
		saveError = null;
	};

	const runBackup = () => {
		confirmTitle = 'Run database backup now?';
		confirmMessage =
			'Streams a full Postgres dump to the configured BACKUP_PATH. Synchronous — the request stays open until the dump finishes. Safe to run at any time.';
		confirmAction = async () => {
			backupBusy = true;
			backupError = null;
			backupLogs = null;
			try {
				const res = await ServerSettingsService.backupDb();
				if (res.ok && res.data && typeof res.data !== 'string') {
					backupLogs = (res.data as { logs: string[] }).logs ?? [];
					showSuccess('Database backup complete');
				} else {
					const data = res.data as { message?: string; data?: string[] } | null;
					backupError = data?.message ?? res.error?.message ?? 'Backup failed';
					if (Array.isArray(data?.data)) backupLogs = data.data;
				}
			} catch (e) {
				backupError = (e as Error).message;
			} finally {
				backupBusy = false;
			}
		};
		confirmOpen = true;
	};

	const runConfirm = async () => {
		await confirmAction();
	};

	// Mail test-send. Blocks on the SMTP round-trip — if that
	// takes >30s the backend returns an error. Persist the SMTP
	// config first if the admin still has unsaved edits, so the
	// probe sees what they just typed.
	const sendTestMail = async () => {
		if (!testMailRecipient || testMailBusy) return;
		testMailBusy = true;
		testMailResult = null;
		try {
			if (isDirty) {
				await save();
			}
			const res = await ServerSettingsService.sendTestMail({
				to: testMailRecipient
			});
			if (res.ok && res.data && typeof res.data !== 'string') {
				testMailResult = {
					ok: true,
					text: `Test email delivered to ${(res.data as { to: string }).to}.`
				};
			} else {
				const data = res.data as { message?: string } | null;
				testMailResult = {
					ok: false,
					text: data?.message ?? res.error?.message ?? 'Test send failed'
				};
			}
		} catch (e) {
			testMailResult = { ok: false, text: (e as Error).message };
		} finally {
			testMailBusy = false;
		}
	};
</script>

<svelte:head>
	<title>Server Settings</title>
</svelte:head>

<div class="flex h-full w-full flex-col overflow-hidden">
	<!-- Page header -->
	<header class="flex items-center justify-between gap-3 border-b px-5 py-3">
		<div class="flex items-center gap-2.5">
			<ServerCogIcon size={18} class="text-muted-foreground" />
			<div class="leading-tight">
				<h1 class="text-sm font-semibold">{irisT("Server Settings", $irisLocale)}</h1>
				<p class="text-2xs text-muted-foreground">
					{irisT("Server-wide configuration. Changes apply immediately.", $irisLocale)}
				</p>
			</div>
		</div>

		<div class="flex items-center gap-1.5">
			<Button
				variant="outline"
				size="sm"
				class="h-7"
				onclick={load}
				disabled={restricted || loading || saving}
			>
				<RefreshCwIcon size={12} class={`mr-1 ${loading ? 'animate-spin' : ''}`} />
				{irisT("Refresh", $irisLocale)}
			</Button>
			<Button
				variant="outline"
				size="sm"
				class="h-7"
				onclick={discard}
				disabled={restricted || saving || !isDirty}
			>
				{irisT("Discard", $irisLocale)}
			</Button>
			<Button size="sm" class="h-7" onclick={save} disabled={restricted || saving || !isDirty}>
				<SaveIcon size={12} class="mr-1" />
				{saving ? irisT("Saving…", $irisLocale) : irisT("Save changes", $irisLocale)}
			</Button>
		</div>
	</header>

	<div class="flex-1 overflow-y-auto p-4">
		{#if restricted}
			<div class="mx-auto max-w-md px-3 py-16 text-center">
				<ShieldAlertIcon size={22} class="mx-auto mb-3 text-muted-foreground" />
				<p class="text-xs font-medium">{irisT("Server settings are not available in demo mode", $irisLocale)}</p>
				<p class="mt-1.5 text-2xs text-muted-foreground">
					{irisT("Mail credentials, integrations and database backups stay with the account that owns this\n\t\t\t\t\tdemo instance. Everything else in Manage IRIS is yours to explore.", $irisLocale)}
				</p>
			</div>
		{:else if loading && payload == null}
			<div class="space-y-2">
				{#each Array(8) as _}
					<Skeleton class="h-10 w-full" />
				{/each}
			</div>
		{:else if payload == null}
			<p class="px-3 py-10 text-center text-xs text-muted-foreground">
				{irisT("No server settings could be loaded.", $irisLocale)}
			</p>
		{:else}
			<div class="flex flex-col gap-5">
				<!-- Versions strip (read-only) -->
				<section class="rounded-md border">
					<header class="border-b bg-muted/30 px-3 py-2">
						<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
							{irisT("Versions", $irisLocale)}
						</h2>
					</header>
					<dl class="grid grid-cols-2 gap-3 p-3 text-2xs sm:grid-cols-3">
						<div>
							<dt class="uppercase tracking-wide text-muted-foreground">{irisT("IRIS", $irisLocale)}</dt>
							<dd class="font-mono">{payload.versions.iris_version}</dd>
						</div>
						<div>
							<dt class="uppercase tracking-wide text-muted-foreground">{irisT("API min / max", $irisLocale)}</dt>
							<dd class="font-mono">
								{payload.versions.api_min} → {payload.versions.api_max}
							</dd>
						</div>
						<div>
							<dt class="uppercase tracking-wide text-muted-foreground">
								{irisT("Module interface min / max", $irisLocale)}
							</dt>
							<dd class="font-mono">
								{payload.versions.module_interface_min} → {payload.versions.module_interface_max}
							</dd>
						</div>
						<div class="sm:col-span-2">
							<dt class="uppercase tracking-wide text-muted-foreground">{irisT("DB revision", $irisLocale)}</dt>
							<dd class="font-mono">{payload.versions.db_revision ?? '—'}</dd>
						</div>
						<div>
							<dt class="uppercase tracking-wide text-muted-foreground">{irisT("Updates available", $irisLocale)}</dt>
							<dd>
								{#if payload.settings.has_updates_available}
									<span
										class="rounded-sm border border-amber-400/40 bg-amber-400/10 px-1.5 py-0 text-2xs text-amber-700 dark:text-amber-300"
									>
										{irisT("Yes — see the changelog", $irisLocale)}
									</span>
								{:else}
									<span class="text-muted-foreground">{irisT("No", $irisLocale)}</span>
								{/if}
							</dd>
						</div>
					</dl>
				</section>

				<!-- Proxy -->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<WifiIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Module HTTP / HTTPS proxy", $irisLocale)}
							</h2>
						</div>
					</header>
					<div class="grid grid-cols-1 gap-3 p-4 text-xs sm:grid-cols-2">
						<div class="flex flex-col gap-1">
							<label
								for="srv-http-proxy"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("HTTP proxy", $irisLocale)}
							</label>
							<Input
								id="srv-http-proxy"
								class="h-7 text-xs"
								placeholder="http://proxy:3128"
								value={String(form.http_proxy ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.http_proxy = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="srv-https-proxy"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("HTTPS proxy", $irisLocale)}
							</label>
							<Input
								id="srv-https-proxy"
								class="h-7 text-xs"
								placeholder="http://proxy:3128"
								value={String(form.https_proxy ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.https_proxy = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<p class="text-2xs text-muted-foreground sm:col-span-2">
							{irisT("Used by IRIS modules that fetch external resources. Empty leaves the system default in\n\t\t\t\t\t\t\tplace.", $irisLocale)}
						</p>
					</div>
				</section>

				<!-- Post-init -->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<PowerIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Post-init behaviour", $irisLocale)}
							</h2>
						</div>
					</header>
					<div class="flex flex-col gap-3 p-4 text-xs">
						<label class="flex items-start gap-2">
							<Switch
								checked={!!form.prevent_post_mod_repush}
								onCheckedChange={(v: boolean) => (form.prevent_post_mod_repush = v)}
								disabled={saving}
							/>
							<div>
								<div class="font-medium">{irisT("Prevent re-registering default modules on boot", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{irisT("Once you've customised an installed module, turn this on to stop the boot routine\n\t\t\t\t\t\t\t\t\tresetting it on the next restart.", $irisLocale)}
								</p>
							</div>
						</label>
						<label class="flex items-start gap-2">
							<Switch
								checked={!!form.prevent_post_objects_repush}
								onCheckedChange={(v: boolean) => (form.prevent_post_objects_repush = v)}
								disabled={saving}
							/>
							<div>
								<div class="font-medium">{irisT("Prevent re-registering default case objects on boot", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{irisT("Same for the seeded taxonomies (asset types, IOC types, classifications, states,\n\t\t\t\t\t\t\t\t\tevidence types). Useful when you've pruned the defaults.", $irisLocale)}
								</p>
							</div>
						</label>
						<label class="flex items-start gap-2">
							<Switch
								checked={!!form.enable_updates_check}
								onCheckedChange={(v: boolean) => (form.enable_updates_check = v)}
								disabled={saving}
							/>
							<div>
								<div class="font-medium">{irisT("Enable periodic update checks", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{irisT("Runs a Celery task on a schedule that polls the IRIS update server. The outcome is\n\t\t\t\t\t\t\t\t\tsurfaced in the read-only \"Updates available\" flag above.", $irisLocale)}
								</p>
							</div>
						</label>
					</div>
				</section>

				<!-- Password policy -->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<KeyRoundIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Password policy", $irisLocale)}
							</h2>
						</div>
					</header>
					<div class="grid grid-cols-1 gap-3 p-4 text-xs sm:grid-cols-2">
						<div class="flex flex-col gap-1">
							<label
								for="srv-pp-len"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Minimum length", $irisLocale)}
							</label>
							<Input
								id="srv-pp-len"
								type="number"
								min={6}
								max={128}
								class="h-7 text-xs"
								value={String(form.password_policy_min_length ?? '')}
								disabled={saving}
								oninput={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value.trim();
									form.password_policy_min_length = raw === '' ? 0 : Number(raw);
								}}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="srv-pp-chars"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Required special characters", $irisLocale)}
							</label>
							<Input
								id="srv-pp-chars"
								class="h-7 text-xs"
								placeholder="!@#$%^&*"
								value={String(form.password_policy_special_chars ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.password_policy_special_chars =
										(e.currentTarget as HTMLInputElement).value || null)}
							/>
							<p class="text-2xs text-muted-foreground">{irisT("Empty = no special-char requirement.", $irisLocale)}</p>
						</div>
						<label class="flex items-start gap-2 sm:col-span-2">
							<Switch
								checked={!!form.password_policy_upper_case}
								onCheckedChange={(v: boolean) => (form.password_policy_upper_case = v)}
								disabled={saving}
							/>
							<span class="text-xs">{irisT("Require at least one uppercase letter", $irisLocale)}</span>
						</label>
						<label class="flex items-start gap-2 sm:col-span-2">
							<Switch
								checked={!!form.password_policy_lower_case}
								onCheckedChange={(v: boolean) => (form.password_policy_lower_case = v)}
								disabled={saving}
							/>
							<span class="text-xs">{irisT("Require at least one lowercase letter", $irisLocale)}</span>
						</label>
						<label class="flex items-start gap-2 sm:col-span-2">
							<Switch
								checked={!!form.password_policy_digit}
								onCheckedChange={(v: boolean) => (form.password_policy_digit = v)}
								disabled={saving}
							/>
							<span class="text-xs">{irisT("Require at least one digit", $irisLocale)}</span>
						</label>
					</div>
				</section>

				<!-- Auth + confirmations -->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<ShieldAlertIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Authentication & safety", $irisLocale)}
							</h2>
						</div>
					</header>
					<div class="flex flex-col gap-3 p-4 text-xs">
						<label class="flex items-start gap-2">
							<Switch
								checked={!mfaLocked && !!form.enforce_mfa}
								onCheckedChange={(v: boolean) => (form.enforce_mfa = v)}
								disabled={saving || mfaLocked}
							/>
							<div>
								<div class="font-medium">{irisT("Enforce MFA", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{#if mfaLocked}{irisT("Unavailable in demo mode — accounts here are shared, so a second factor bound to\n\t\t\t\t\t\t\t\t\t\tone visitor's authenticator would lock everyone else out.", $irisLocale)}{:else}{irisT("Forces every user to register a TOTP / WebAuthn factor at next login. Existing\n\t\t\t\t\t\t\t\t\t\tsessions stay valid until they expire.", $irisLocale)}{/if}
								</p>
							</div>
						</label>
						<label class="flex items-start gap-2">
							<Switch
								checked={!!form.force_confirmation_before_delete}
								onCheckedChange={(v: boolean) => (form.force_confirmation_before_delete = v)}
								disabled={saving}
							/>
							<div>
								<div class="font-medium">{irisT("Require confirmation before delete", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{irisT("Adds a \"type the name to confirm\" prompt on every destructive action.", $irisLocale)}
								</p>
							</div>
						</label>
					</div>
				</section>

				<!--
				  Mail — outbound (SMTP).
				  Password field is treated as "write-only" — the backend
				  never returns it. When `mail_smtp_password_set` is
				  true we render a "•••••" placeholder so the admin
				  knows a password is stored; typing anything replaces
				  it. Empty submit = clear.
				-->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<MailIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Outbound mail (SMTP)", $irisLocale)}
							</h2>
						</div>
						<div class="flex items-center gap-2">
							<span class="text-2xs text-muted-foreground">{irisT("Enabled", $irisLocale)}</span>
							<Switch
								checked={!!form.mail_smtp_enabled}
								onCheckedChange={(v: boolean) => (form.mail_smtp_enabled = v)}
								disabled={saving}
							/>
						</div>
					</header>
					<div class="grid grid-cols-1 gap-3 p-4 text-xs sm:grid-cols-2">
						<div class="flex flex-col gap-1">
							<label
								for="smtp-host"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("SMTP host", $irisLocale)}</label
							>
							<Input
								id="smtp-host"
								class="h-7 text-xs"
								placeholder={irisT("smtp.example.com", $irisLocale)}
								value={String(form.mail_smtp_host ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_smtp_host = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="smtp-port"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Port", $irisLocale)}</label
							>
							<Input
								id="smtp-port"
								class="h-7 text-xs"
								type="number"
								placeholder="587"
								value={String(form.mail_smtp_port ?? '')}
								disabled={saving}
								oninput={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value;
									form.mail_smtp_port = raw === '' ? null : Number(raw);
								}}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="smtp-user"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Username", $irisLocale)}</label
							>
							<Input
								id="smtp-user"
								class="h-7 text-xs"
								value={String(form.mail_smtp_user ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_smtp_user = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="smtp-pass"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Password", $irisLocale)}
								{#if payload?.settings.mail_smtp_password_set}
									<span class="ml-1 text-muted-foreground/70">{irisT("(stored — leave blank to keep)", $irisLocale)}</span>
								{/if}
							</label>
							<Input
								id="smtp-pass"
								class="h-7 text-xs"
								type="password"
								placeholder={payload?.settings.mail_smtp_password_set ? '•••••••••' : ''}
								value={String(form.mail_smtp_password ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_smtp_password = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<label class="flex cursor-pointer items-center gap-2 sm:col-span-1">
							<Switch
								checked={!!form.mail_smtp_use_tls}
								onCheckedChange={(v: boolean) => (form.mail_smtp_use_tls = v)}
								disabled={saving}
							/>
							<span class="text-2xs">{irisT("STARTTLS", $irisLocale)}</span>
						</label>
						<label class="flex cursor-pointer items-center gap-2 sm:col-span-1">
							<Switch
								checked={!!form.mail_smtp_use_ssl}
								onCheckedChange={(v: boolean) => (form.mail_smtp_use_ssl = v)}
								disabled={saving}
							/>
							<span class="text-2xs">{irisT("Implicit SSL", $irisLocale)}</span>
						</label>
						<div class="flex flex-col gap-1">
							<label
								for="smtp-from-addr"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("From address", $irisLocale)}</label
							>
							<Input
								id="smtp-from-addr"
								class="h-7 text-xs"
								placeholder={irisT("iris@example.com", $irisLocale)}
								value={String(form.mail_from_address ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_from_address = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="smtp-from-name"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("From name (optional)", $irisLocale)}</label
							>
							<Input
								id="smtp-from-name"
								class="h-7 text-xs"
								placeholder={irisT("IRIS Notifications", $irisLocale)}
								value={String(form.mail_from_name ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_from_name = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>

						<!-- Test send -->
						<div class="flex flex-col gap-2 rounded-md border-t pt-3 sm:col-span-2">
							<label
								for="smtp-test-to"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Send a test email", $irisLocale)}
							</label>
							<div class="flex items-center gap-2">
								<Input
									id="smtp-test-to"
									class="h-7 flex-1 text-xs"
									placeholder={irisT("you@example.com", $irisLocale)}
									type="email"
									value={testMailRecipient}
									disabled={testMailBusy}
									oninput={(e) => (testMailRecipient = (e.currentTarget as HTMLInputElement).value)}
								/>
								<Button
									size="sm"
									class="h-7"
									onclick={sendTestMail}
									disabled={testMailBusy || !testMailRecipient}
								>
									<SendIcon size={12} class="mr-1" />
									{testMailBusy ? irisT("Sending…", $irisLocale) : irisT("Send test", $irisLocale)}
								</Button>
							</div>
							{#if testMailResult}
								<p class="text-2xs {testMailResult.ok ? 'text-emerald-600' : 'text-destructive'}">
									{testMailResult.text}
								</p>
							{/if}
							<p class="text-2xs text-muted-foreground">
								{irisT("Sends synchronously using the SMTP config above. Any unsaved edits are saved first.", $irisLocale)}
							</p>
						</div>
					</div>
				</section>

				<!--
				  Mail — inbound (IMAP).
				  Poll interval is applied on save (the backend refreshes
				  the Celery beat schedule live). The rules driving what
				  each inbound message becomes are on the /settings/mail
				  page.
				-->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<InboxIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Inbound mail (IMAP)", $irisLocale)}
							</h2>
						</div>
						<div class="flex items-center gap-2">
							<span class="text-2xs text-muted-foreground">{irisT("Enabled", $irisLocale)}</span>
							<Switch
								checked={!!form.mail_imap_enabled}
								onCheckedChange={(v: boolean) => (form.mail_imap_enabled = v)}
								disabled={saving}
							/>
						</div>
					</header>
					<div class="grid grid-cols-1 gap-3 p-4 text-xs sm:grid-cols-2">
						<div class="flex flex-col gap-1">
							<label
								for="imap-host"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("IMAP host", $irisLocale)}</label
							>
							<Input
								id="imap-host"
								class="h-7 text-xs"
								placeholder={irisT("imap.example.com", $irisLocale)}
								value={String(form.mail_imap_host ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_imap_host = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="imap-port"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Port", $irisLocale)}</label
							>
							<Input
								id="imap-port"
								class="h-7 text-xs"
								type="number"
								placeholder="993"
								value={String(form.mail_imap_port ?? '')}
								disabled={saving}
								oninput={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value;
									form.mail_imap_port = raw === '' ? null : Number(raw);
								}}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="imap-user"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Username", $irisLocale)}</label
							>
							<Input
								id="imap-user"
								class="h-7 text-xs"
								value={String(form.mail_imap_user ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_imap_user = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="imap-pass"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Password", $irisLocale)}
								{#if payload?.settings.mail_imap_password_set}
									<span class="ml-1 text-muted-foreground/70">{irisT("(stored — leave blank to keep)", $irisLocale)}</span>
								{/if}
							</label>
							<Input
								id="imap-pass"
								class="h-7 text-xs"
								type="password"
								placeholder={payload?.settings.mail_imap_password_set ? '•••••••••' : ''}
								value={String(form.mail_imap_password ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_imap_password = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<label class="flex cursor-pointer items-center gap-2 sm:col-span-1">
							<Switch
								checked={!!form.mail_imap_use_ssl}
								onCheckedChange={(v: boolean) => (form.mail_imap_use_ssl = v)}
								disabled={saving}
							/>
							<span class="text-2xs">{irisT("Use SSL", $irisLocale)}</span>
						</label>
						<div class="flex flex-col gap-1">
							<label
								for="imap-mailbox"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Mailbox", $irisLocale)}</label
							>
							<Input
								id="imap-mailbox"
								class="h-7 text-xs"
								placeholder={irisT("INBOX", $irisLocale)}
								value={String(form.mail_imap_mailbox ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.mail_imap_mailbox = (e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="imap-poll"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Poll interval (sec)", $irisLocale)}</label
							>
							<Input
								id="imap-poll"
								class="h-7 text-xs"
								type="number"
								min="60"
								placeholder="300"
								value={String(form.mail_imap_poll_interval_sec ?? '')}
								disabled={saving}
								oninput={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value;
									form.mail_imap_poll_interval_sec = raw === '' ? null : Number(raw);
								}}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="imap-attach-mb"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
								>{irisT("Max attachment (MB)", $irisLocale)}</label
							>
							<Input
								id="imap-attach-mb"
								class="h-7 text-xs"
								type="number"
								min="1"
								placeholder="20"
								value={String(form.mail_imap_max_attachment_mb ?? '')}
								disabled={saving}
								oninput={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value;
									form.mail_imap_max_attachment_mb = raw === '' ? null : Number(raw);
								}}
							/>
						</div>
						<p class="text-2xs text-muted-foreground sm:col-span-2">
							{irisT("Poll cadence is capped at ≥60s server-side to avoid hammering the IMAP endpoint. Rules\n\t\t\t\t\t\t\tthat decide what each inbound message becomes live on the", $irisLocale)}
							<a class="underline hover:text-foreground" href="/settings/mail">{irisT("Mail rules", $irisLocale)}</a> {irisT("page.", $irisLocale)}
						</p>
					</div>
				</section>

				<!-- Error reporting -->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<BugIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Error reporting", $irisLocale)}
							</h2>
						</div>
					</header>
					<div class="grid grid-cols-1 gap-3 p-4 text-xs sm:grid-cols-2">
						<label class="flex items-start gap-2 sm:col-span-2">
							<Switch
								checked={!!form.error_reporting_enabled}
								onCheckedChange={(v: boolean) => (form.error_reporting_enabled = v)}
								disabled={saving}
							/>
							<div>
								<div class="font-medium">{irisT("Enable error reporting", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{irisT("When on, unhandled exceptions on the server and in the browser are forwarded to a\n\t\t\t\t\t\t\t\t\tSentry-compatible collector (Sentry, GlitchTip, or compatible). Payloads are\n\t\t\t\t\t\t\t\t\tredacted server-side before send — case content, credentials, and sensitive\n\t\t\t\t\t\t\t\t\theaders never leave the box.", $irisLocale)}
								</p>
							</div>
						</label>
						<div class="flex flex-col gap-1 sm:col-span-2">
							<label
								for="srv-err-backend-dsn"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Backend DSN", $irisLocale)}
							</label>
							<Input
								id="srv-err-backend-dsn"
								type="password"
								autocomplete="off"
								class="h-7 text-xs"
								placeholder={form.error_reporting_backend_dsn_set
									? irisT("•••••• (unchanged — leave blank to keep)", $irisLocale)
									: 'https://<key>@collector.example/1'}
								value={String(form.error_reporting_backend_dsn ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.error_reporting_backend_dsn =
										(e.currentTarget as HTMLInputElement).value || null)}
							/>
							<p class="text-2xs text-muted-foreground">
								{irisT("Stored encrypted at rest. Leave blank to keep the current value; type a new DSN to\n\t\t\t\t\t\t\t\treplace it. Server exception captures use this DSN only.", $irisLocale)}
							</p>
						</div>
						<div class="flex flex-col gap-1 sm:col-span-2">
							<label
								for="srv-err-frontend-dsn"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Frontend DSN", $irisLocale)}
							</label>
							<Input
								id="srv-err-frontend-dsn"
								class="h-7 text-xs"
								placeholder="https://<key>@collector.example/2"
								value={String(form.error_reporting_frontend_dsn ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.error_reporting_frontend_dsn =
										(e.currentTarget as HTMLInputElement).value || null)}
							/>
							<p class="text-2xs text-muted-foreground">
								{irisT("Handed to the browser at boot via", $irisLocale)} <code>/api/v2/runtime-config</code>{irisT(". Reload the\n\t\t\t\t\t\t\t\tpage after changing so the browser SDK picks up the new value.", $irisLocale)}
							</p>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="srv-err-env"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Environment tag", $irisLocale)}
							</label>
							<Input
								id="srv-err-env"
								class="h-7 text-xs"
								placeholder={irisT("prod / staging / dev-local", $irisLocale)}
								value={String(form.error_reporting_environment ?? '')}
								disabled={saving}
								oninput={(e) =>
									(form.error_reporting_environment =
										(e.currentTarget as HTMLInputElement).value || null)}
							/>
						</div>
						<div class="flex flex-col gap-1">
							<label
								for="srv-err-sample"
								class="text-2xs font-medium uppercase tracking-wide text-muted-foreground"
							>
								{irisT("Sample rate (0.0 – 1.0)", $irisLocale)}
							</label>
							<Input
								id="srv-err-sample"
								type="number"
								min={0}
								max={1}
								step={0.05}
								class="h-7 text-xs"
								value={String(form.error_reporting_sample_rate ?? '')}
								disabled={saving}
								oninput={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value.trim();
									form.error_reporting_sample_rate = raw === '' ? null : Number(raw);
								}}
							/>
						</div>
						<label class="flex items-start gap-2 sm:col-span-2">
							<Switch
								checked={!!form.error_reporting_include_user}
								onCheckedChange={(v: boolean) => (form.error_reporting_include_user = v)}
								disabled={saving}
							/>
							<div>
								<div class="font-medium">{irisT("Attach user identity to events", $irisLocale)}</div>
								<p class="text-2xs text-muted-foreground">
									{irisT("Off by default. When on, the acting user's id and username are attached to each\n\t\t\t\t\t\t\t\t\tcaptured event. No email or PII beyond the username is sent.", $irisLocale)}
								</p>
							</div>
						</label>
					</div>
				</section>

				<!-- Save error feedback (sits at the bottom so admins
				     don't have to scroll back up after a save). -->
				{#if saveError}
					<p class="whitespace-pre-wrap text-2xs text-destructive">{saveError}</p>
				{/if}

				<!-- DB backup -->
				<section class="rounded-md border">
					<header class="flex items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
						<div class="flex items-center gap-2">
							<DatabaseIcon size={14} class="text-muted-foreground" />
							<h2 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
								{irisT("Database backup", $irisLocale)}
							</h2>
						</div>
						<Button size="sm" class="h-7" onclick={runBackup} disabled={backupBusy}>
							<DatabaseIcon size={12} class="mr-1" />
							{backupBusy ? irisT("Running…", $irisLocale) : irisT("Run backup now", $irisLocale)}
						</Button>
					</header>
					<div class="flex flex-col gap-2 p-4 text-xs">
						<p class="text-2xs text-muted-foreground">
							{irisT("Triggers an immediate `pg_dump` of the IRIS database to the path configured in\n\t\t\t\t\t\t\t`BACKUP_PATH`. The button stays disabled while the dump runs.", $irisLocale)}
						</p>
						{#if backupLogs && backupLogs.length > 0}
							<pre
								class="max-h-64 overflow-y-auto rounded-md border bg-muted/30 p-2 font-mono text-2xs">{backupLogs.join(
									'\n'
								)}</pre>
						{/if}
						{#if backupError}
							<p class="whitespace-pre-wrap text-2xs text-destructive">{backupError}</p>
						{/if}
					</div>
				</section>
			</div>
		{/if}
	</div>
</div>

<ConfirmationDialog
	bind:open={confirmOpen}
	title={confirmTitle}
	message={confirmMessage}
	confirmText="Run backup"
	onConfirm={runConfirm}
/>
