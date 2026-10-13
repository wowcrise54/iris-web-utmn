<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/state';
	import { beforeNavigate } from '$app/navigation';
	import {
		FileText,
		Download,
		Printer,
		RefreshCw,
		Save,
		Clock,
		User,
		ShieldCheck
	} from 'lucide-svelte';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { timezone } from '$lib/stores/timezone.store.svelte';
	import {
		CASE_ACCESS_CTX,
		type CaseAccessContext
	} from '$lib/contexts/case-access.context.svelte';
	import { CaseDatastoreService } from '$lib/services/case-datastore.service';
	import { IncidentCardService, IncidentCardError } from '$lib/services/incident-card.service';
	import type { IncidentCard, CardExport, CardValue } from '$lib/types/resources/incident-card';
	import { cardPayload } from '$lib/utils/incident-card';
	import CardField from './CardField.svelte';
	const locale = useLocale();
	const access = getContext<CaseAccessContext>(CASE_ACCESS_CTX);
	const ru = $derived($locale === 'ru');
	const caseId = $derived(Number(page.params.case_id));
	const zone = $derived(timezone.preference === 'browser' ? 'Asia/Yekaterinburg' : timezone.zone);
	let card = $state<IncidentCard | null>(null),
		baseline = $state(''),
		busy = $state(false),
		error = $state(''),
		conflict = $state(false),
		snapshot = $state<CardExport | null>(null);
	let mounted = $state(false);
	let editing = $state(false);
	let snapshotZone = '';
	let generation = 0;
	const dirty = $derived(card !== null && JSON.stringify(cardPayload(card)) !== baseline);
	const editable = $derived(editing && access?.canEdit() === true && !busy);
	const tr = (r: string, e: string) => (ru ? r : e);
	function date(value: string | null) {
		return value
			? new Intl.DateTimeFormat(ru ? 'ru-RU' : 'en-GB', {
					dateStyle: 'medium',
					timeStyle: 'short',
					timeZone: zone
				}).format(new Date(value))
			: '—';
	}
	function duration(value: number | null) {
		if (value === null) return tr('Не определено', 'Not determined');
		return `${Math.floor(value / 3600)} ${tr('ч', 'h')} ${Math.floor((value % 3600) / 60)} ${tr('мин', 'min')} ${Math.floor(value % 60)} ${tr('с', 's')}`;
	}
	function accept(value: IncidentCard) {
		card = value;
		baseline = JSON.stringify(cardPayload(value));
		snapshot = null;
		conflict = false;
		editing = false;
	}
	async function load() {
		const id = caseId,
			version = ++generation;
		busy = true;
		error = '';
		try {
			const value = await IncidentCardService.get(id);
			if (version === generation && id === caseId) accept(value);
		} catch (e) {
			if (version === generation) error = String(e instanceof Error ? e.message : e);
		} finally {
			if (version === generation) busy = false;
		}
	}
	$effect(() => {
		const id = caseId;
		if (mounted && id) {
			card = null;
			baseline = '';
			snapshot = null;
			conflict = false;
			editing = false;
			void load();
		}
	});
	onMount(() => {
		mounted = true;
		const unload = (event: BeforeUnloadEvent) => {
			if (dirty) {
				event.preventDefault();
				event.returnValue = '';
			}
		};
		window.addEventListener('beforeunload', unload);
		return () => {
			generation++;
			window.removeEventListener('beforeunload', unload);
		};
	});
	beforeNavigate((nav) => {
		if (
			dirty &&
			!window.confirm(
				tr(
					'Есть несохранённые изменения. Выйти и отбросить их?',
					'Unsaved changes. Leave and discard them?'
				)
			)
		)
			nav.cancel();
	});
	function reload() {
		if (
			!dirty ||
			window.confirm(
				tr(
					'Отбросить несохранённые изменения и загрузить текущую карточку?',
					'Discard unsaved changes and reload the current card?'
				)
			)
		)
			void load();
	}
	function cancelEdit() {
		if (dirty) reload();
		else editing = false;
	}
	function edit(key: string, value: CardValue, mode: 'auto' | 'manual' = 'manual') {
		if (!card || !editable) return;
		card.fields[key] = {
			...card.fields[key],
			value,
			mode,
			status: mode === 'manual' ? 'manual' : 'ok'
		};
		snapshot = null;
	}
	async function save() {
		if (!card || !editable || conflict) return;
		const id = caseId,
			version = generation,
			draft = JSON.parse(JSON.stringify(card)) as IncidentCard;
		busy = true;
		error = '';
		try {
			const value = await IncidentCardService.save(id, draft);
			if (version === generation && id === caseId) accept(value);
		} catch (e) {
			if (version === generation) {
				conflict = e instanceof IncidentCardError && e.status === 409;
				error = conflict
					? tr(
							'Карточку изменил другой пользователь. Ваш черновик сохранён на экране. Перезагрузите после проверки изменений.',
							'Another user changed this card. Your draft is preserved on screen. Reload after reviewing your changes.'
						)
					: String(e instanceof Error ? e.message : e);
			}
		} finally {
			if (version === generation) busy = false;
		}
	}
	const pickers = [
		{
			key: 'alert_id',
			source: 'alerts',
			ru: 'Исходный алёрт',
			en: 'Source alert',
			multiple: false
		},
		{
			key: 'affected_asset_ids',
			source: 'assets',
			ru: 'Затронутые активы',
			en: 'Affected assets',
			multiple: true
		},
		{
			key: 'source_asset_id',
			source: 'assets',
			ru: 'Актив-источник',
			en: 'Source asset',
			multiple: false
		},
		{
			key: 'target_asset_id',
			source: 'assets',
			ru: 'Актив-цель',
			en: 'Target asset',
			multiple: false
		},
		{
			key: 'ioc_ids',
			source: 'iocs',
			ru: 'Индикаторы компрометации',
			en: 'Indicators of compromise',
			multiple: true
		},
		{
			key: 'file_ids',
			source: 'files',
			ru: 'Файлы / доказательства',
			en: 'Files / evidence',
			multiple: true
		},
		{
			key: 'performed_task_ids',
			source: 'tasks',
			ru: 'Выполненные мероприятия',
			en: 'Performed actions',
			multiple: true
		},
		{
			key: 'planned_task_ids',
			source: 'tasks',
			ru: 'Планируемые мероприятия',
			en: 'Planned actions',
			multiple: true
		}
	] as const;
	function selection(key: keyof IncidentCard['selections'], value: number | null | number[]) {
		if (card && editable) {
			(card.selections as Record<string, number | null | number[]>)[key] = value;
			snapshot = null;
		}
	}
	async function downloadFile(fileId: number, label: string) {
		const id = caseId;
		try {
			const file = await CaseDatastoreService.fetchFileBlobUrl(id, fileId);
			if (!file) throw new Error(tr('Не удалось загрузить файл', 'Could not download file'));
			if (id !== caseId) {
				URL.revokeObjectURL(file.url);
				return;
			}
			const link = document.createElement('a');
			link.href = file.url;
			link.download = file.filename || label;
			document.body.appendChild(link);
			link.click();
			link.remove();
			setTimeout(() => URL.revokeObjectURL(file.url), 60000);
		} catch (e) {
			error = String(e instanceof Error ? e.message : e);
		}
	}
	async function exportCard(kind: 'docx' | 'print') {
		if (!card || dirty || busy) return;
		if (
			card.completeness.missing.length &&
			!window.confirm(
				tr(
					'Карточка заполнена не полностью. Продолжить экспорт?',
					'The card is incomplete. Continue export?'
				)
			)
		)
			return;
		const printWindow = kind === 'print' ? window.open('about:blank', '_blank') : null;
		if (kind === 'print' && !printWindow) {
			error = tr('Разрешите всплывающие окна для печати.', 'Allow popups to print.');
			return;
		}
		if (printWindow) printWindow.opener = null;
		const exportZone = zone;
		const id = caseId,
			version = generation;
		busy = true;
		error = '';
		try {
			const output =
				snapshot && snapshotZone === exportZone
					? snapshot
					: await IncidentCardService.export(id, exportZone);
			if (version !== generation || id !== caseId) {
				printWindow?.close();
				return;
			}
			snapshot = output;
			snapshotZone = exportZone;
			if (kind === 'docx') {
				const bytes = Uint8Array.from(atob(output.docx_base64), (c) => c.charCodeAt(0));
				const url = URL.createObjectURL(
					new Blob([bytes], {
						type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
					})
				);
				const link = document.createElement('a');
				link.href = url;
				link.download = output.filename;
				link.click();
				setTimeout(() => URL.revokeObjectURL(url), 60000);
			} else {
				const url = URL.createObjectURL(
					new Blob([output.html], { type: 'text/html;charset=utf-8' })
				);
				printWindow?.location.replace(url);
				setTimeout(() => URL.revokeObjectURL(url), 60000);
			}
		} catch (e) {
			printWindow?.close();
			if (version === generation) error = String(e instanceof Error ? e.message : e);
		} finally {
			if (version === generation) busy = false;
		}
	}
</script>

<svelte:head
	><title>{irisT('Incident card', $locale)} {irisT('· IRIS', $locale)}</title></svelte:head
>
<div class="card-page">
	<header class="hero">
		<div class="title">
			<span class="icon"><FileText size={26} /></span>
			<div>
				<p class="eyebrow">IRIS · {tr('Кейс', 'Case')} #{caseId}</p>
				<h1>{tr('Карточка инцидента', 'Incident card')}</h1>
				<p class="subtitle">
					{tr('Приложение 4 · Единая карточка учёта инцидента', 'Appendix 4 · Incident record')}
				</p>
			</div>
		</div>
		<div class="actions">
			<button onclick={reload} disabled={busy}
				><RefreshCw size={16} />{tr('Обновить', 'Refresh')}</button
			>{#if access?.canEdit() && card}{#if editing}<button
						class="primary"
						onclick={save}
						disabled={!dirty || busy || conflict}
						><Save size={16} />{tr('Сохранить', 'Save')}</button
					><button onclick={cancelEdit} disabled={busy}>{tr('Отмена', 'Cancel')}</button
					>{:else}<button class="primary" onclick={() => (editing = true)} disabled={busy}
						>{tr('Редактировать', 'Edit')}</button
					>{/if}{/if}<button onclick={() => exportCard('docx')} disabled={dirty || busy || !card}
				><Download size={16} />DOCX</button
			><button onclick={() => exportCard('print')} disabled={dirty || busy || !card}
				><Printer size={16} />{tr('Печать / PDF', 'Print / PDF')}</button
			>
		</div>
	</header>
	{#if error}<div role="alert" class="notice error">
			{error}{#if conflict}<button onclick={reload}
					>{tr('Перезагрузить и отбросить черновик', 'Reload and discard draft')}</button
				>{/if}
		</div>{/if}
	{#if dirty}<div role="status" class="notice">
			{tr(
				'Изменения не сохранены. Сохраните или отбросьте их перед экспортом. Автополя пересчитываются при сохранении.',
				'Unsaved changes. Save or discard before export. Auto fields refresh on save.'
			)}<button onclick={reload}>{tr('Отбросить', 'Discard')}</button>
		</div>{/if}
	{#if busy && !card}<p role="status">{tr('Загрузка карточки…', 'Loading card…')}</p>{/if}
	{#if card}
		<section class="panel metadata">
			<div>
				<User size={16} /><span
					>{tr('Автор', 'Author')}<strong>{card.meta.author ?? '—'}</strong></span
				>
			</div>
			<div>
				<Clock size={16} /><span
					>{tr('Создана', 'Created')}<strong>{date(card.meta.created_at)}</strong></span
				>
			</div>
			<div>
				<Clock size={16} /><span
					>{tr('Изменена', 'Modified')}<strong>{date(card.meta.updated_at)}</strong></span
				>
			</div>
			<div>
				<ShieldCheck size={16} /><span
					>{tr('Статус кейса', 'Case status')}<strong>{irisT(card.meta.status, $locale)}</strong
					></span
				>
			</div>
			<div>
				<Clock size={16} /><span
					>{tr('Время реагирования', 'Reaction time')}<strong
						>{duration(card.derived.reaction_seconds)}</strong
					></span
				>
			</div>
			<div>
				<Clock size={16} /><span
					>{tr('Продолжительность инцидента', 'Incident duration')}<strong
						>{duration(card.derived.incident_duration_seconds)}</strong
					></span
				>
			</div>
			<div>
				<span
					>{tr('Важность / приоритет', 'Importance / priority')}<strong
						>{card.derived.importance === 'low'
							? tr('Низкая', 'Low')
							: card.derived.importance === 'medium'
								? tr('Средняя', 'Medium')
								: card.derived.importance === 'high'
									? tr('Высокая', 'High')
									: tr('Не определено', 'Not determined')} / {card.derived.priority ?? '—'}</strong
					></span
				>
			</div>
		</section>
		<div class="completeness">
			<span
				>{tr('Заполнено', 'Completed')}: {card.completeness.filled} / {card.completeness
					.total}</span
			><span
				>{zone} · {tr('Версия', 'Revision')}
				{card.revision}{snapshot ? ` · ${tr('Экспорт', 'Export')} #${snapshot.revision}` : ''}</span
			>
		</div>
		{#if card.completeness.missing.length || card.warnings.length}<details class="panel warnings">
				<summary
					>{tr('Проверка полноты и предупреждения', 'Completeness and warnings')} ({card
						.completeness.missing.length + card.warnings.length})</summary
				>
				<ul>
					{#each card.completeness.missing as key}<li>
							{card.catalog.sections.flatMap((s) => s.fields).find((f) => f.key === key)?.[
								ru ? 'label_ru' : 'label_en'
							] ?? key}
						</li>{/each}{#each card.warnings as warning}<li>{warning}</li>{/each}
				</ul>
			</details>{/if}
		<details class="panel" open={editing}>
			<summary>{tr('Источники и связи', 'Sources and relations')}</summary>
			<p class="subtitle">
				{tr(
					'Выберите связи явно. Роли активов не определяются автоматически. Изменение связей обновит автополя после сохранения.',
					'Choose explicit relations. Asset roles are not inferred. Source changes refresh auto fields after saving.'
				)}
			</p>
			<div class="grid">
				{#each pickers as picker}<div class="picker">
						<label for={`source-${picker.key}`}>{ru ? picker.ru : picker.en}</label
						>{#if picker.multiple}<div id={`source-${picker.key}`} class="source-list">
								{#each card.sources[picker.source] as source}<label
										><input
											type="checkbox"
											disabled={!editable}
											checked={(card.selections[picker.key] as number[]).includes(source.id)}
											onchange={(e) => {
												const current = card!.selections[picker.key] as number[];
												selection(
													picker.key,
													e.currentTarget.checked
														? [...current, source.id]
														: current.filter((id) => id !== source.id)
												);
											}}
										/>{source.label}</label
									>{#if picker.source === 'files' && card.selections.file_ids.includes(source.id)}<button
											onclick={() => downloadFile(source.id, source.label)}
											><Download size={14} />{tr('Скачать', 'Download')}</button
										>{/if}{:else}<span class="subtitle">—</span>{/each}
							</div>{:else}<select
								id={`source-${picker.key}`}
								disabled={!editable}
								value={card.selections[picker.key] ?? ''}
								onchange={(e) =>
									selection(
										picker.key,
										e.currentTarget.value ? Number(e.currentTarget.value) : null
									)}
								><option value="">—</option>{#each card.sources[picker.source] as source}<option
										value={source.id}>{source.label}</option
									>{/each}</select
							>{/if}
					</div>{/each}
			</div>
		</details>
		{#each card.catalog.sections as section, index}<details class="panel section" open={index < 2}>
				<summary
					><span class="section-index">{String(index + 1).padStart(2, '0')}</span>{ru
						? section.label_ru
						: section.label_en}<small>{section.fields.length} {tr('полей', 'fields')}</small
					></summary
				>
				<div class="grid">
					{#each section.fields as definition}<CardField
							{definition}
							field={card.fields[definition.key] ?? {
								value: null,
								mode: 'auto',
								source: null,
								status: 'missing'
							}}
							{ru}
							{editable}
							view={!editing}
							{zone}
							onchange={(value, mode) => edit(definition.key, value, mode)}
						/>{/each}
				</div>
			</details>{/each}
		<p class="footer">
			{tr(
				'Печать открывает сохранённый документ. Используйте Ctrl+P и выберите «Сохранить как PDF». DOCX и печатный документ используют один снимок карточки.',
				'Print opens the saved document. Use Ctrl+P and choose Save as PDF. DOCX and print share one card snapshot.'
			)}
		</p>
	{/if}
</div>

<style>
	.card-page {
		width: 100%;
		max-width: 1440px;
		margin: 0 auto;
		padding: 2rem;
		color: hsl(var(--foreground));
	}
	.hero {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1.5rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}
	.title {
		display: flex;
		align-items: center;
		gap: 1rem;
	}
	.icon {
		padding: 0.9rem;
		border-radius: 1rem;
		background: hsl(var(--primary) / 0.1);
		color: hsl(var(--primary));
	}
	h1 {
		font-size: 1.7rem;
		font-weight: 650;
		letter-spacing: -0.04em;
	}
	.eyebrow {
		font-size: 0.7rem;
		letter-spacing: 0.1em;
		color: hsl(var(--muted-foreground));
		text-transform: uppercase;
	}
	.subtitle,
	.footer {
		color: hsl(var(--muted-foreground));
		font-size: 0.8rem;
	}
	.actions {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		border: 1px solid hsl(var(--border));
		border-radius: 0.6rem;
		padding: 0.55rem 0.8rem;
		font-size: 0.8rem;
		background: hsl(var(--card));
	}
	button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	button.primary {
		background: hsl(var(--primary));
		color: hsl(var(--primary-foreground));
	}
	.panel {
		background: hsl(var(--card));
		border: 1px solid hsl(var(--border));
		border-radius: 1rem;
		padding: 1.25rem 1.5rem;
		margin-bottom: 1rem;
		box-shadow: 0 2px 6px #00000004;
	}
	.metadata {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1.5rem;
	}
	.metadata > div {
		display: flex;
		gap: 0.6rem;
		font-size: 0.75rem;
		color: hsl(var(--muted-foreground));
	}
	.metadata strong {
		display: block;
		color: hsl(var(--foreground));
		font-weight: 500;
		margin-top: 0.3rem;
	}
	.completeness {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		font-size: 0.75rem;
		color: hsl(var(--muted-foreground));
		margin: 1.3rem 0.25rem;
	}
	summary {
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		list-style-position: inside;
	}
	summary small {
		float: right;
		color: hsl(var(--muted-foreground));
		font-size: 0.7rem;
		font-weight: 400;
	}
	.section-index {
		font-size: 0.75rem;
		color: hsl(var(--primary));
		margin-right: 0.8rem;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		column-gap: 2rem;
	}
	.picker {
		padding: 1rem 0;
	}
	.picker > label {
		display: block;
		font-size: 0.8rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
	}
	.source-list {
		max-height: 180px;
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		font-size: 0.8rem;
	}
	.source-list label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	select {
		width: 100%;
		border: 1px solid hsl(var(--border));
		border-radius: 0.5rem;
		padding: 0.6rem;
		background: hsl(var(--background));
		color: inherit;
	}
	.notice {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem;
		border-radius: 0.7rem;
		background: hsl(var(--muted));
		font-size: 0.8rem;
		margin-bottom: 1rem;
	}
	.error {
		color: hsl(var(--destructive));
		border: 1px solid hsl(var(--destructive) / 0.4);
	}
	.warnings ul {
		font-size: 0.8rem;
		margin: 1rem 0 0 1.5rem;
		list-style: disc;
	}
	.footer {
		padding: 0.5rem;
		text-align: center;
	}
	@media (max-width: 800px) {
		.card-page {
			padding: 1rem;
		}
		.grid {
			grid-template-columns: 1fr;
		}
		.panel {
			padding: 1rem;
		}
		.metadata {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.actions {
			width: 100%;
		}
		h1 {
			font-size: 1.3rem;
		}
		summary small {
			float: none;
			margin-left: 0.5rem;
		}
	}
</style>
