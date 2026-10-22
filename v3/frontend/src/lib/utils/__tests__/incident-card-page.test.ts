vi.mock('svelte', async () => {
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
vi.mock('$app/state', () => ({ page: { params: { case_id: '2' } } }));
vi.mock('$app/navigation', () => ({ beforeNavigate: vi.fn() }));
vi.mock('$lib/services/incident-card.service', () => ({
	IncidentCardService: { get: vi.fn(), save: vi.fn(), export: vi.fn() },
	IncidentCardError: class extends Error {
		status = 409;
	}
}));
import { render, fireEvent, screen, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import IncidentPage from '../../../routes/(app)/case/[case_id]/incident-card/+page.svelte';
import { IncidentCardService, IncidentCardError } from '$lib/services/incident-card.service';
import { CASE_ACCESS_CTX } from '$lib/contexts/case-access.context.svelte';
import type { IncidentCard } from '$lib/types/resources/incident-card';
const fixture: IncidentCard = {
	schema_version: 1,
	revision: 1,
	meta: { case_id: 2 },
	fields: {
		description: { value: 'Incident overview', mode: 'auto', source: 'case', status: 'ok' }
	},
	selections: {},
	derived: {
		importance: 'low',
		priority: 1,
		incident_duration_seconds: null
	},
	catalog: {
		sections: [
			{
				id: 'general',
				label_ru: 'Общие сведения',
				label_en: 'General',
				fields: [
					{
						key: 'description',
						label_ru: 'Описание',
						label_en: 'Description',
						type: 'text',
						auto: true
					}
				]
			}
		]
	},
	warnings: []
};
function mount(canEdit = true) {
	return render(IncidentPage, {
		context: new Map([[CASE_ACCESS_CTX, { canEdit: () => canEdit }]])
	});
}
beforeEach(() => {
	vi.mocked(IncidentCardService.get).mockResolvedValue(structuredClone(fixture));
	vi.mocked(IncidentCardService.save).mockResolvedValue(structuredClone(fixture));
});
describe('incident card view/edit session', () => {
	it('reveals unacceptable event options only for Yes without losing previous selections', async () => {
		const conditional = structuredClone(fixture);
		conditional.fields = {
			unacceptable_event: { value: false, mode: 'manual', source: null, status: 'manual' },
			unacceptable_event_kinds: { value: ['leak'], mode: 'manual', source: null, status: 'manual' }
		};
		conditional.catalog.sections = [
			{
				id: 'unacceptable_event',
				label_ru: 'Недопустимое событие',
				label_en: 'Unacceptable event',
				fields: [
					{
						key: 'unacceptable_event',
						label_ru: 'Недопустимое событие',
						label_en: 'Unacceptable event flag',
						type: 'boolean',
						auto: false
					},
					{
						key: 'unacceptable_event_kinds',
						label_ru: 'Виды',
						label_en: 'Event kinds',
						type: 'multichoice',
						auto: false,
						options: [{ value: 'leak', label_ru: 'Утечка', label_en: 'Leak' }]
					}
				]
			}
		];
		vi.mocked(IncidentCardService.get).mockResolvedValueOnce(conditional);
		mount();
		await screen.findByText('Unacceptable event');
		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		expect(screen.queryByRole('checkbox', { name: 'Leak' })).not.toBeInTheDocument();
		await fireEvent.change(screen.getByLabelText('Unacceptable event flag'), {
			target: { value: 'true' }
		});
		expect(screen.getByRole('checkbox', { name: 'Leak' })).toBeChecked();
	});

	it('keeps calculation tables in the logical priority block, separate from investigation', async () => {
		const grouped = structuredClone(fixture);
		grouped.catalog.sections = [
			{
				id: 'priority',
				label_ru: 'Приоритизация инцидента',
				label_en: 'Prioritization',
				fields: []
			},
			{
				id: 'investigation',
				label_ru: 'Расследование инцидента',
				label_en: 'Investigation',
				fields: []
			}
		];
		vi.mocked(IncidentCardService.get).mockResolvedValueOnce(grouped);
		mount();
		const priority = (await screen.findByText('Prioritization')).closest('details')!;
		const investigation = screen.getByText('Investigation').closest('details')!;
		expect(priority.querySelectorAll('table')).toHaveLength(2);
		expect(investigation.querySelectorAll('table')).toHaveLength(0);
	});
	it('shows only the form and no removed metadata or relationship blocks', async () => {
		mount();
		await screen.findByText('Incident overview');
		for (const text of [
			'Sources and relations',
			'Author',
			'Created',
			'Modified',
			'Case status',
			'Reaction time',
			'Completed',
			'Revision',
			'1 fields'
		])
			expect(screen.queryByText(text)).not.toBeInTheDocument();
	});
	it('starts in readable view and opens editable inputs only after Edit', async () => {
		mount();
		await screen.findByText('Incident overview');
		expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		expect(screen.getByLabelText('Description')).toBeEnabled();
		expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
	});
	it('successful save returns to view', async () => {
		mount();
		await screen.findByText('Incident overview');
		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		await fireEvent.input(screen.getByLabelText('Description'), { target: { value: 'Updated' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.queryByRole('textbox')).not.toBeInTheDocument());
		expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
	});
	it('read-only access has no Edit action', async () => {
		mount(false);
		await screen.findByText('Incident overview');
		expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
		expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
	});
	it('keeps an unsaved edit when discard confirmation is declined', async () => {
		const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
		mount();
		await screen.findByText('Incident overview');
		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		await fireEvent.input(screen.getByLabelText('Description'), { target: { value: 'Draft' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(screen.getByLabelText('Description')).toHaveValue('Draft');
		expect(confirm).toHaveBeenCalledOnce();
		confirm.mockRestore();
	});
	it('keeps conflict draft in editing mode and blocks repeated save', async () => {
		vi.mocked(IncidentCardService.save).mockRejectedValueOnce(
			new IncidentCardError(409, 'Conflict')
		);
		mount();
		await screen.findByText('Incident overview');
		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		await fireEvent.input(screen.getByLabelText('Description'), { target: { value: 'Draft' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await screen.findByRole('alert');
		expect(screen.getByLabelText('Description')).toHaveValue('Draft');
		expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
	});
});
