import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => {
	const clientEntry = '../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import IocDataTable from '$lib/components/common/ioc/IocDataTable.svelte';
import type { Ioc } from '$lib/types/resources/ioc';

const makeIoc = (value: string): Ioc => ({
	ioc_id: 7,
	ioc_uuid: 'layout-fixture',
	ioc_value: value,
	ioc_type_id: 1,
	ioc_type: {
		type_id: 1,
		type_name: 'sha256',
		type_description: '',
		type_taxonomy: null,
		type_validation_regex: null,
		type_validation_expect: null
	},
	ioc_tlp_id: 1,
	tlp: { tlp_id: 1, tlp_name: 'amber+strict', tlp_bscolor: '' },
	ioc_description: 'Automatically extracted from a synthetic event',
	ioc_tags: 'fixture',
	user_id: 1,
	ioc_misp: null,
	ioc_enrichment: null,
	link: null,
	custom_attributes: null,
	modification_history: null
});

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

describe('IOC table values', () => {
	it.each(['a'.repeat(64), 'https://example.test/' + 'segment'.repeat(80)])(
		'keeps the complete alert value available for inspection and copying',
		async (value) => {
			const writeText = vi.fn().mockResolvedValue(undefined);
			vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
			render(IocDataTable, {
				iocs: [makeIoc(value)],
				tablePage: 1,
				showDescription: true,
				showTags: true
			});
			expect(screen.getByTitle(value).textContent?.trim()).toBe(value);
			await fireEvent.click(screen.getByRole('button', { name: 'Copy IOC value' }));
			expect(writeText).toHaveBeenCalledExactlyOnceWith(value);
			expect(document.querySelector('button button')).toBeNull();
			expect(screen.getByText('sha256')).toBeTruthy();
			expect(screen.getByText('OpenCTI · Not checked')).toBeTruthy();
		}
	);

	it('retains the case IOC link alongside the full copyable value', async () => {
		const value = 'b'.repeat(64);
		const writeText = vi.fn().mockResolvedValue(undefined);
		vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
		render(IocDataTable, { iocs: [makeIoc(value)], tablePage: 1, caseId: 23, selectionMode: true });
		expect(screen.queryByRole('button', { name: 'Filter by' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Sort by' })).toBeNull();
		expect(screen.getByRole('link').getAttribute('href')).toBe('/case/23/iocs/7');
		await fireEvent.click(screen.getByRole('button', { name: 'Copy IOC value' }));
		expect(writeText).toHaveBeenCalledExactlyOnceWith(value);
	});
});
