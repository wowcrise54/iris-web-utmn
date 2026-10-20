<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { page } from '$app/state';
	import { beforeNavigate } from '$app/navigation';
	import { FileText, Download, Printer, RefreshCw, Save } from 'lucide-svelte';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import { timezone } from '$lib/stores/timezone.store.svelte';
	import {
		CASE_ACCESS_CTX,
		type CaseAccessContext
	} from '$lib/contexts/case-access.context.svelte';
	import { IncidentCardService, IncidentCardError } from '$lib/services/incident-card.service';
	import type { IncidentCard, CardExport, CardValue } from '$lib/types/resources/incident-card';
	import { cardPayload, deriveCard } from '$lib/utils/incident-card';
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
	const calculations = $derived(deriveCard(card?.fields ?? {}));
	const endDefinition = $derived(
		card?.catalog.sections.flatMap((s) => s.fields).find((f) => f.key === 'incident_ended_at')
	);

	function duration(value: number | null) {
		if (value === null) return tr('Не определено', 'Not determined');
		return `${Math.floor(value / 86400)} ${tr('дн.', 'd')} ${Math.floor((value % 86400) / 3600)} ${tr('ч', 'h')} ${Math.floor((value % 3600) / 60)} ${tr('мин', 'min')} ${Math.floor(value % 60)} ${tr('с', 's')}`;
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
		const previous = card.fields[key]?.value;
		card.fields[key] = {
			...card.fields[key],
			value,
			mode,
			status: mode === 'manual' ? 'manual' : 'ok'
		};
		if (key === 'completed' && value === true && previous !== true) {
			card.fields.incident_ended_at = {
				value: new Date().toISOString(),
				mode: 'manual',
				source: null,
				status: 'manual'
			};
		}
		if (key === 'categories' || key === 'prioritization_type') {
			card.fields.priority_override = {
				value: null,
				mode: 'auto',
				source: null,
				status: 'missing'
			};
		}
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
	async function exportCard(kind: 'docx' | 'print') {
		if (!card || dirty || busy) return;
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
				<h1>{tr('Карточка данных об инциденте', 'Incident record')}</h1>
				<p class="subtitle">
					{tr('Приложение № 4', 'Appendix 4 · Incident record')}
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
				'Изменения не сохранены. Сохраните или отбросьте их перед экспортом. ',
				'Unsaved changes. Save or discard before export. '
			)}<button onclick={reload}>{tr('Отбросить', 'Discard')}</button>
		</div>{/if}
	{#if busy && !card}<p role="status">{tr('Загрузка карточки…', 'Loading card…')}</p>{/if}
	{#if card}
		<div class="sections">
			{#each card.catalog.sections as section, index}<details
					class="panel section"
					class:half={section.id === 'actors' || section.id === 'motives'}
					open={index < 2}
				>
					<summary
						><span class="section-index">{String(index + 1).padStart(2, '0')}</span>{ru
							? section.label_ru
							: section.label_en}</summary
					>
					{#if section.id === 'priority'}
						<div class="calculation">
							<p>
								{tr('Важность инцидента по таблице:', 'Incident importance:')}
								<strong
									>{calculations.importance === 'low'
										? tr('Низкая', 'Low')
										: calculations.importance === 'medium'
											? tr('Средняя', 'Medium')
											: calculations.importance === 'high'
												? tr('Высокая', 'High')
												: '—'}</strong
								>
							</p>
							<table>
								<thead
									><tr
										><th>{tr('Категория инцидента/тип системы', 'Category/system type')}</th><th
											>{tr('Вспомогательная', 'Auxiliary')}</th
										><th>{tr('Ключевая', 'Key')}</th><th>{tr('Целевая', 'Target')}</th></tr
									></thead
								><tbody>
									{#each [['Средняя', 'Высокая', 'Высокая'], ['Высокая', 'Высокая', 'Высокая'], ['Средняя', 'Высокая', 'Высокая'], ['Низкая', 'Средняя', 'Средняя'], ['Низкая', 'Низкая', 'Средняя'], ['Низкая', 'Средняя', 'Средняя'], ['Низкая', 'Низкая', 'Низкая']] as row, i}<tr
											><td>{tr('Категория', 'Category')} {i + 1}</td>{#each row as cell}<td
													>{cell}</td
												>{/each}</tr
										>{/each}
								</tbody>
							</table>
							<p>
								{tr('Приоритет инцидента по таблице:', 'Incident priority:')}
								<strong>{calculations.priority ?? '—'}</strong>
							</p>
							<table>
								<thead
									><tr
										><th>{tr('Тип системы/Важность', 'System type/Importance')}</th><th
											>{tr('Низкая', 'Low')}</th
										><th>{tr('Средняя', 'Medium')}</th><th>{tr('Высокая', 'High')}</th></tr
									></thead
								><tbody>
									{#each [[tr('Вспомогательная', 'Auxiliary'), 9, 8, 6], [tr('Ключевая', 'Key'), 7, 5, 3], [tr('Целевая', 'Target'), 4, 2, 1]] as row}<tr
											>{#each row as cell}<td>{cell}</td>{/each}</tr
										>{/each}
								</tbody>
							</table>
						</div>
					{/if}
					<div class="grid" class:single={section.fields.length === 1}>
						{#each section.fields as definition}{#if (definition.key !== 'unacceptable_event_kinds' || card.fields.unacceptable_event?.value === true) && (definition.key !== 'incident_ended_at' || card.fields.completed?.value !== true)}<CardField
									{definition}
									field={definition.key === 'priority_override' &&
									card.fields[definition.key]?.mode === 'auto'
										? { ...card.fields[definition.key], value: calculations.priority }
										: (card.fields[definition.key] ?? {
												value: null,
												mode: 'auto',
												source: null,
												status: 'missing'
											})}
									{ru}
									{editable}
									view={!editing}
									{zone}
									onchange={(value, mode) => edit(definition.key, value, mode)}
								/>{#if definition.key === 'completed' && card.fields.completed?.value === true}<div
										class="field-duration"
									>
										{#if endDefinition}<CardField
												definition={endDefinition}
												field={card.fields.incident_ended_at}
												{ru}
												{editable}
												view={!editing}
												{zone}
												onchange={(value, mode) => edit('incident_ended_at', value, mode)}
											/>{/if}
										<p>
											{tr(
												'Если «да», то уточнить, как долго длился инцидент в днях/часах/минутах',
												'Incident duration in days/hours/minutes'
											)}
										</p>
										{#if calculations.incident_duration_seconds !== null}<strong
												>{duration(calculations.incident_duration_seconds)}</strong
											>{:else}<p role="status">
												{tr(
													'Укажите дату и время возникновения инцидента для расчёта длительности.',
													'Enter the occurrence date and time to calculate duration.'
												)}
											</p>{/if}
									</div>{/if}{/if}{/each}
					</div>
				</details>{/each}
		</div>
		<p class="footer">
			{tr(
				'Печать открывает сохранённый документ. Используйте Ctrl+P и выберите «Сохранить как PDF». DOCX и печатный документ используют один снимок карточки.',
				'Print opens the saved document. Use Ctrl+P and choose Save as PDF. DOCX and print share one card snapshot.'
			)}
		</p>
	{/if}
</div>

<style>
	.sections {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.sections > .section {
		grid-column: 1 / -1;
		margin-bottom: 0;
	}
	.sections > .section.half {
		grid-column: auto;
		align-self: start;
	}
	.grid.single {
		grid-template-columns: minmax(0, 1fr);
	}
	@media (max-width: 900px) {
		.sections {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	.calculation table {
		width: 100%;
		border-collapse: collapse;
		margin: 1rem 0;
		font-size: 0.85rem;
	}
	.calculation th,
	.calculation td {
		border: 1px solid hsl(var(--border));
		padding: 0.4rem;
		text-align: left;
	}
	.field-duration {
		padding: 1rem 0;
	}
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
	summary {
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		list-style-position: inside;
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
		.actions {
			width: 100%;
		}
		h1 {
			font-size: 1.3rem;
		}
	}
</style>
