<script lang="ts">
	import { translate as irisT } from '$lib/i18n/context';
	import type { CardDefinition, CardField, CardValue } from '$lib/types/resources/incident-card';
	import { toLocalInput, fromLocalInput } from '$lib/utils/incident-card';
	let {
		definition,
		field,
		ru = false,
		editable = false,
		view = false,
		zone,
		onchange
	}: {
		definition: CardDefinition;
		field: CardField;
		ru?: boolean;
		editable?: boolean;
		view?: boolean;
		zone: string;
		onchange: (value: CardValue, mode?: 'auto' | 'manual') => void;
	} = $props();
	let dateError = $state('');
	const label = $derived(ru ? definition.label_ru : definition.label_en);
	const people = $derived(
		Array.isArray(field.value) ? (field.value as { name: string; position: string }[]) : []
	);
	function setDate(value: string) {
		try {
			onchange(value ? fromLocalInput(value, zone) : null);
			dateError = '';
		} catch (e) {
			dateError = e instanceof Error ? e.message : String(e);
		}
	}
	function person(index: number, key: 'name' | 'position', value: string) {
		onchange(people.map((p, i) => (i === index ? { ...p, [key]: value } : p)));
	}
	function displayValue(value: CardValue): string {
		if (value === null || value === '') return '—';
		if (Array.isArray(value)) return value.map(displayValue).join(', ') || '—';
		if (definition.type === 'boolean') return value ? (ru ? 'Да' : 'Yes') : ru ? 'Нет' : 'No';
		if (definition.type === 'datetime')
			return new Intl.DateTimeFormat(ru ? 'ru-RU' : 'en-GB', {
				dateStyle: 'medium',
				timeStyle: 'short',
				timeZone: zone
			}).format(new Date(String(value)));
		const option = definition.options?.find((option) => option.value === value);
		return option ? (ru ? option.label_ru : option.label_en) : String(value);
	}
</script>

<div class="field">
	<div class="field-label">
		<label for={`card-${definition.key}`}>{label}</label><span
			class:manual={field.mode === 'manual'}
			>{field.mode === 'manual' ? (ru ? 'Вручную' : 'Manual') : ru ? 'Авто' : 'Auto'}</span
		>
	</div>
	{#if view}
		<div class="display-value" id={`card-${definition.key}`}>
			{#if definition.type === 'people'}
				{#each people as person}<p>
						{person.name || '—'}{person.position ? ` · ${person.position}` : ''}
					</p>{:else}—{/each}
			{:else}{displayValue(field.value)}{/if}
		</div>
	{:else if definition.type === 'people'}
		<div id={`card-${definition.key}`}>
			{#each people as p, i}<div class="person">
					<input
						aria-label={`${label}: ${irisT('Name', ru ? 'ru' : 'en')} ${i + 1}`}
						value={p.name}
						disabled={!editable}
						placeholder={ru ? 'ФИО' : 'Name'}
						oninput={(e) => person(i, 'name', e.currentTarget.value)}
					/><input
						aria-label={`${label}: ${irisT('Position', ru ? 'ru' : 'en')} ${i + 1}`}
						value={p.position}
						disabled={!editable}
						placeholder={ru ? 'Должность' : 'Position'}
						oninput={(e) => person(i, 'position', e.currentTarget.value)}
					/>{#if editable}<button
							onclick={() => onchange(people.filter((_, j) => j !== i))}
							aria-label={irisT('Remove person', ru ? 'ru' : 'en')}>×</button
						>{/if}
				</div>{/each}
			{#if editable}<button
					class="minor"
					onclick={() => onchange([...people, { name: '', position: '' }])}
					>{ru ? '+ Добавить участника' : '+ Add person'}</button
				>{:else if !people.length}<p>—</p>{/if}
		</div>
	{:else if definition.type === 'textarea'}
		<textarea
			id={`card-${definition.key}`}
			value={String(field.value ?? '')}
			disabled={!editable}
			rows="4"
			oninput={(e) => onchange(e.currentTarget.value)}
		></textarea>
	{:else if definition.type === 'datetime'}
		<input
			id={`card-${definition.key}`}
			type="datetime-local"
			step="1"
			value={toLocalInput(String(field.value ?? ''), zone)}
			disabled={!editable}
			onchange={(e) => setDate(e.currentTarget.value)}
		/><small>{zone}</small>{#if dateError}<p role="alert" class="text-destructive">
				{dateError}
			</p>{/if}
	{:else if definition.type === 'choice' || definition.type === 'boolean' || definition.type === 'multichoice'}
		{#if definition.type === 'multichoice'}
			<div id={`card-${definition.key}`} class="choices">
				{#each definition.options ?? [] as option}<label
						><input
							type="checkbox"
							disabled={!editable}
							checked={Array.isArray(field.value) && field.value.includes(option.value)}
							onchange={(e) =>
								onchange(
									e.currentTarget.checked
										? [...(Array.isArray(field.value) ? field.value : []), option.value]
										: (Array.isArray(field.value) ? field.value : []).filter(
												(v) => v !== option.value
											)
								)}
						/>{ru ? option.label_ru : option.label_en}</label
					>{/each}
			</div>
		{:else}<select
				id={`card-${definition.key}`}
				value={field.value === null ? '' : String(field.value)}
				disabled={!editable}
				onchange={(e) => {
					const value = e.currentTarget.value;
					onchange(
						value === ''
							? null
							: definition.type === 'boolean'
								? value === 'true'
								: (definition.options?.find((o) => String(o.value) === value)?.value ?? value)
					);
				}}
				><option value="">—</option>{#if definition.type === 'boolean'}<option value="true"
						>{ru ? 'Да' : 'Yes'}</option
					><option value="false">{ru ? 'Нет' : 'No'}</option
					>{:else}{#each definition.options ?? [] as option}<option value={String(option.value)}
							>{ru ? option.label_ru : option.label_en}</option
						>{/each}{/if}</select
			>{/if}
	{:else}<input
			id={`card-${definition.key}`}
			value={String(field.value ?? '')}
			disabled={!editable}
			oninput={(e) => onchange(e.currentTarget.value)}
		/>{/if}
	<div class="provenance">
		<small
			>{field.source ?? (ru ? 'Нет источника' : 'No source')} · {field.status === 'missing'
				? ru
					? 'Не заполнено'
					: 'Missing'
				: field.status === 'manual'
					? ru
						? 'Ручное значение'
						: 'Manual value'
					: ru
						? 'Заполнено'
						: 'Available'}</small
		>{#if !view && editable && definition.auto && field.mode === 'manual'}<button
				class="minor"
				onclick={() => onchange(field.value, 'auto')}>{ru ? 'Вернуть авто' : 'Restore auto'}</button
			>{/if}
	</div>
</div>

<style>
	.display-value {
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		min-height: 1.5rem;
		font-size: 0.95rem;
	}
	.field {
		padding: 1rem 0;
		border-bottom: 1px solid hsl(var(--border));
		min-width: 0;
	}
	.field-label {
		display: flex;
		gap: 0.75rem;
		align-items: center;
		margin-bottom: 0.5rem;
		font-weight: 600;
	}
	.field-label span {
		font-size: 0.65rem;
		font-weight: 400;
		background: hsl(var(--muted));
		border-radius: 1rem;
		padding: 0.15rem 0.5rem;
	}
	.field-label .manual {
		color: hsl(var(--primary));
	}
	input:not([type='checkbox']),
	textarea,
	select {
		width: 100%;
		padding: 0.6rem 0.75rem;
		border: 1px solid hsl(var(--border));
		border-radius: 0.5rem;
		background: hsl(var(--background));
		color: inherit;
	}
	input:disabled,
	textarea:disabled,
	select:disabled {
		opacity: 1;
		background: transparent;
		border-color: transparent;
		padding-left: 0;
	}
	textarea {
		resize: vertical;
	}
	.provenance {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: 0.4rem;
		color: hsl(var(--muted-foreground));
		font-size: 0.75rem;
	}
	.minor {
		color: hsl(var(--primary));
		font-size: 0.75rem;
	}
	.person {
		display: flex;
		gap: 0.5rem;
		margin: 0.5rem 0;
	}
	.choices {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
	}
	.choices label {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	small {
		font-size: 0.75rem;
		color: hsl(var(--muted-foreground));
	}
</style>
