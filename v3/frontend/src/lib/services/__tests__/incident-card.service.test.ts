import { describe, it, expect, vi } from 'vitest';
import { IncidentCardService, IncidentCardError } from '../incident-card.service';
import { ApiService } from '../api.service';
vi.mock('../api.service', () => ({ ApiService: { get: vi.fn(), put: vi.fn() } }));
describe('incident card service', () => {
	it('retains HTTP conflict status for draft recovery', async () => {
		vi.mocked(ApiService.put).mockResolvedValue({
			ok: false,
			status: 409,
			data: null,
			error: { status: 409, type: 'conflict', message: 'Concurrent edit' }
		});
		try {
			await IncidentCardService.save(2, {
				schema_version: 1,
				revision: 4,
				fields: {},
				selections: {}
			} as any);
			expect.fail('must reject');
		} catch (e) {
			expect(e).toBeInstanceOf(IncidentCardError);
			expect((e as IncidentCardError).status).toBe(409);
		}
	});
	it('reads case-scoped data', async () => {
		vi.mocked(ApiService.get).mockResolvedValue({ ok: true, status: 200, data: { revision: 3 } });
		expect(await IncidentCardService.get(2)).toEqual({ revision: 3 });
		expect(ApiService.get).toHaveBeenCalledWith('/cases/2/incident-card', {});
	});
	it('exports both formats from one response', async () => {
		const output = {
			filename: 'card.docx',
			docx_base64: 'AA==',
			html: '<p>x</p>',
			revision: 4,
			warnings: []
		};
		vi.mocked(ApiService.get).mockResolvedValue({ ok: true, status: 200, data: output });
		expect(await IncidentCardService.export(2)).toEqual(output);
	});
});
