vi.mock('svelte', async () => {
	// Use the client runtime only in this component suite; global browser conditions change fetch mocks.
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
import { render, fireEvent, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import CardField from '../../../routes/(app)/case/[case_id]/incident-card/CardField.svelte';
describe('incident card field UX', () => {
	it('exposes incident type choices in named groups and preserves independent repeated labels', async () => {
		const onchange = vi.fn();
		render(CardField, {
			definition: {
				key: 'incident_types',
				label_ru: 'Тип инцидента',
				label_en: 'Incident type',
				type: 'multichoice',
				auto: false,
				options: [
					{
						value: 'fire',
						label_ru: 'Пожар',
						label_en: 'Fire',
						group_ru: 'Естественный',
						group_en: 'Natural'
					},
					{
						value: 'fire_repeat',
						label_ru: 'Пожар',
						label_en: 'Fire',
						group_ru: 'Естественный',
						group_en: 'Natural'
					}
				]
			},
			field: { ...field, value: [] },
			zone: 'UTC',
			editable: true,
			onchange
		});
		expect(screen.getByRole('group', { name: 'Natural' })).toBeInTheDocument();
		const boxes = screen.getAllByRole('checkbox', { name: 'Fire' });
		await fireEvent.click(boxes[1]);
		expect(onchange).toHaveBeenCalledWith(['fire_repeat']);
	});

	it('does not add automatic/manual metadata to the regulation field', () => {
		render(CardField, { definition, field, zone: 'UTC', view: true, onchange: vi.fn() });
		expect(screen.queryByText('Auto')).not.toBeInTheDocument();
		expect(screen.queryByText('Manual')).not.toBeInTheDocument();
	});
	const definition = {
		key: 'description',
		label_ru: 'Описание',
		label_en: 'Description',
		type: 'textarea' as const,
		auto: true
	};
	const field = {
		value: 'Source description',
		mode: 'auto' as const,
		source: 'case',
		status: 'ok' as const
	};
	it('locks field for read-only case access', () => {
		render(CardField, { definition, field, zone: 'UTC', editable: false, onchange: vi.fn() });
		expect(screen.getByLabelText('Description')).toBeDisabled();
	});
	it('manual typing updates value and offers restore on manual field', async () => {
		const onchange = vi.fn();
		render(CardField, {
			definition,
			field: { ...field, mode: 'manual' },
			zone: 'UTC',
			editable: true,
			onchange
		});
		await fireEvent.input(screen.getByLabelText('Description'), { target: { value: 'Edited' } });
		expect(onchange).toHaveBeenCalledWith('Edited');
		await fireEvent.click(screen.getByText('Restore auto'));
		expect(onchange).toHaveBeenCalledWith('Source description', 'auto');
	});
	it('renders each repeated person with name and position', () => {
		render(CardField, {
			definition: { ...definition, type: 'people' },
			field: { ...field, value: [{ name: 'Alice', position: 'Analyst' }] },
			zone: 'UTC',
			editable: true,
			onchange: vi.fn()
		});
		expect(screen.getByLabelText('Description: Name 1')).toHaveValue('Alice');
		expect(screen.getByLabelText('Description: Position 1')).toHaveValue('Analyst');
	});
});
