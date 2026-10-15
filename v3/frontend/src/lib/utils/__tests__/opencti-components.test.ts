import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => {
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
import { cleanup, render, screen } from '@testing-library/svelte';
import OpenCTIEnrichment from '$lib/components/common/OpenCTIEnrichment.svelte';
import OpenCTICaseSummary from '$lib/components/common/OpenCTICaseSummary.svelte';

afterEach(cleanup);

describe('OpenCTI views', () => {
	it('renders nothing before the module has written enrichment', () => {
		const { container } = render(OpenCTIEnrichment, { enrichment: { vt: {} } });
		expect(container.querySelector('section')).toBeNull();
	});
	it('shows observables and revoked indicators separately', () => {
		render(OpenCTIEnrichment, { enrichment: { opencti: {
			status: 'matched', checked_at: '2026-10-15T00:00:00Z',
			observables: [{ id: 'one', observable_value: 'example.org' }],
			indicators: [{ id: 'two', name: 'Indicator fixture', validity: 'revoked', url: 'https://cti.example/indicator/two' }]
		} } });
		expect(screen.getByText('Observables (1)')).toBeTruthy();
		expect(screen.getByText('Indicators (1)')).toBeTruthy();
		expect(screen.getByText('Revoked')).toBeTruthy();
		expect(screen.getByRole('link', { name: 'Indicator fixture' }).getAttribute('href')).toBe('https://cti.example/indicator/two');
	});
	it('keeps remote HTML as text and rejects unsafe links', () => {
		const { container } = render(OpenCTIEnrichment, { enrichment: { opencti: {
			status: 'matched', observables: [{ id: 'one', url: 'javascript:alert(1)', description: '<img src=x onerror=alert(1)>' }]
		} } });
		expect(container.querySelector('img')).toBeNull();
		expect(container.querySelector('a')).toBeNull();
	});

	it('shows the persisted case summary including linked alert IOCs', () => {
		render(OpenCTICaseSummary, { attributes: { __iris_opencti: { value: JSON.stringify({
			schema_version: 1, total: 2, counts: { matched: 1, no_match: 1 },
			iocs: [{ value: 'example.org', status: 'matched' }, { value: 'linked-alert.org', status: 'no_match' }]
		}) } } });
		expect(screen.getByText('linked-alert.org')).toBeTruthy();
		expect(screen.getByText(/Case and linked alert IOCs: 2/)).toBeTruthy();
	});
});
