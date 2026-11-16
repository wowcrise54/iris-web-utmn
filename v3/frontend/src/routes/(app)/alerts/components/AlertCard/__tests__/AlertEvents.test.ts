import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import AlertEvents from '../AlertEvents.svelte';

vi.mock('svelte', async () => {
	const clientEntry = '../../../../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
vi.mock('$lib/components/ui/clipboard-copy/clipboard-copy.svelte', () => ({ default: () => {} }));

afterEach(cleanup);

it('opens the JSON of a selected child event and identifies missing children', async () => {
	render(AlertEvents, {
		source: {
			events: [
				{ uuid: 'root', text: 'Correlation rule' },
				{ _meta: { id: 'child' }, text: 'Process started', 'event_src.host': 'host-01' }
			],
			event_tree: [
				{ uuid: 'root', subevents: [{ uuid: 'child' }, { uuid: 'missing', missing: true }] }
			]
		}
	});

	expect(screen.queryByText('Process started')).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: 'Expand related events' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Process started' }));
	await fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
	expect(screen.getByText(/"event_src.host": "host-01"/)).toBeInTheDocument();
	expect(screen.queryByText(/"text": "Correlation rule"/)).toBeNull();
	expect(screen.getByText('Event data unavailable')).toBeInTheDocument();
});

it('shows events imported without a tree', async () => {
	render(AlertEvents, { source: { events: [{ text: 'Legacy event', action: 'access' }] } });

	await fireEvent.click(screen.getByRole('button', { name: 'Legacy event' }));
	expect(screen.getByText('access')).toBeInTheDocument();
});
