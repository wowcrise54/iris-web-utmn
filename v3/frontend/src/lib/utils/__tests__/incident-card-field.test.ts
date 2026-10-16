vi.mock('svelte', async () => {
	// Use the client runtime only in this component suite; global browser conditions change fetch mocks.
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
import { render, fireEvent, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import CardField from '../../../routes/(app)/case/[case_id]/incident-card/CardField.svelte';
describe('incident card field UX', () => {
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
