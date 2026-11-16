import { render, fireEvent, screen, waitFor, cleanup, within } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import Page from '../+page.svelte';
import { ModulesService } from '$lib/services/modules.service';

vi.mock('svelte', async () => {
	const clientEntry = '../../../../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
vi.mock('$lib/services/modules.service', () => ({
	ModulesService: { list: vi.fn(), listHooks: vi.fn(), get: vi.fn(), setParameter: vi.fn(), enable: vi.fn() }
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('renders Wazuh settings, saves a masked password, and enables the module', async () => {
	vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} unobserve() {} });
	const detail = {
		id: 9, module_name: 'iris_wazuh_module', module_human_name: 'Wazuh Indexer',
		module_description: '', module_version: '1.0', interface_version: '1.2.0',
		date_added: null, is_active: false, has_pipeline: false, module_type: 'module_processor',
		module_config: [
			{ param_name: 'password', param_human_name: 'Indexer password', type: 'sensitive_string', value: '', mandatory: true },
			{ param_name: 'min_level', param_human_name: 'Minimum Wazuh level', type: 'string', value: '12', mandatory: true }
		]
	};
	const page = (data: unknown[]) => ({ ok: true, data: { data, total: data.length, next_page: null } });
	vi.mocked(ModulesService.list).mockResolvedValue(page([{ ...detail, configured: true, added_by: '' }]) as never);
	vi.mocked(ModulesService.listHooks).mockResolvedValue(page([]) as never);
	vi.mocked(ModulesService.get).mockResolvedValue({ ok: true, data: detail } as never);
	vi.mocked(ModulesService.setParameter).mockResolvedValue({ ok: true, data: detail } as never);
	vi.mocked(ModulesService.enable).mockImplementation(async () => {
		detail.is_active = true;
		return { ok: true, data: detail } as never;
	});
	render(Page);
	await fireEvent.click(await screen.findByRole('button', { name: 'Wazuh Indexer' }));
	const label = await screen.findByText('Indexer password');
	const row = label.closest('div.flex.flex-col.gap-2.p-3') as HTMLElement;
	const input = row.querySelector('input[type="password"]') as HTMLInputElement;
	expect(input).toBeTruthy();
	expect(screen.getByDisplayValue('12')).toBeTruthy();
	await fireEvent.input(input, { target: { value: 'test-secret' } });
	await fireEvent.click(within(row).getByRole('button', { name: 'Save' }));
	await waitFor(() => expect(ModulesService.setParameter).toHaveBeenCalledWith(9, 'password', 'test-secret'));
	await waitFor(() => expect(input.value).toBe(''));
	await fireEvent.click(screen.getByRole('switch'));
	await waitFor(() => expect(ModulesService.enable).toHaveBeenCalledWith(9));
	await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'));
});
