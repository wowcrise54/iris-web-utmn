import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import AnalysisPage from '../../routes/(app)/case/[case_id]/analysis/+page.svelte';
import { EvidenceAnalysisService } from './evidence-analysis.service';
import { CaseDatastoreService } from './case-datastore.service';

vi.mock('svelte', async () => {
	const clientEntry = '../../../node_modules/svelte/src/index-client.js';
	return import(clientEntry) as Promise<typeof import('svelte')>;
});
vi.mock('$app/state', () => ({
	page: { params: { case_id: '1' }, url: new URL('https://iris.test/case/1/analysis?analysis=10') }
}));
vi.mock('./evidence-analysis.service', () => ({
	EvidenceAnalysisService: { list: vi.fn(), get: vi.fn(), start: vi.fn(), resume: vi.fn() }
}));
vi.mock('./case-datastore.service', () => ({ CaseDatastoreService: { listFiles: vi.fn() } }));
vi.mock('vis-network', () => ({
	Network: class {
		on() {}
		off() {}
		destroy() {}
		setOptions() {}
		fit() {}
	}
}));
const job = {
	id: 10,
	case_id: 1,
	kind: 'pcap',
	status: 'completed',
	progress: 1,
	total: 1,
	error: null,
	conversation_id: null,
	source_url: '',
	result: {
		packets: 1,
		bytes: 100,
		nodes: [
			{ id: '10.0.0.1', label: '10.0.0.1', group: 'host' },
			{ id: '1.1.1.1', label: '1.1.1.1', group: 'host' }
		],
		edges: [
			{
				id: '1',
				from: '10.0.0.1',
				to: '1.1.1.1',
				port: '53',
				protocol: 'DNS',
				packets: 1,
				bytes: 100,
				first_frame: 7,
				first_seen: 1700000000,
				last_seen: 1700000000,
				label: 'DNS'
			}
		],
		indicators: [{ value: 'example.org', frame: 7, timestamp: 1700000000 }]
	}
};
const reply = (data: unknown) => ({ ok: true, data }) as never;
beforeEach(() => {
	vi.stubGlobal(
		'matchMedia',
		vi.fn((query: string) => ({
			matches: false,
			media: query,
			onchange: null,
			addListener() {},
			removeListener() {},
			addEventListener() {},
			removeEventListener() {},
			dispatchEvent() {
				return true;
			}
		}))
	);
	vi.stubGlobal(
		'ResizeObserver',
		class {
			observe() {}
			disconnect() {}
		}
	);
	vi.mocked(EvidenceAnalysisService.list).mockResolvedValue(reply({ analyses: [job] }));
	vi.mocked(EvidenceAnalysisService.get).mockResolvedValue(reply(job));
	vi.mocked(CaseDatastoreService.listFiles).mockResolvedValue(
		reply({ data: [{ file_id: 20, file_original_name: 'capture.pcap' }], next_page: null })
	);
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
	vi.unstubAllGlobals();
});
describe('Evidence analysis viewer', () => {
	it('shows graph-connected flows with packet references and metadata only', async () => {
		const { container } = render(AnalysisPage);
		await waitFor(() =>
			expect(screen.getByText('example.org · #7 · 2023-11-14T22:13:20.000Z')).toBeTruthy()
		);
		expect(container.querySelector('.vis-network-host')?.classList.contains('h-full')).toBe(true);
		expect(screen.getByText('10.0.0.1 → 1.1.1.1:53')).toBeTruthy();
		expect(EvidenceAnalysisService.get).toHaveBeenCalledWith(1, 10);
	});
	it('starts a local file job with identifiers rather than binary upload', async () => {
		vi.mocked(EvidenceAnalysisService.start).mockResolvedValue(reply(job));
		render(AnalysisPage);
		await waitFor(() =>
			expect(screen.getByRole('option', { name: '#20 · capture.pcap' })).toBeTruthy()
		);
		await fireEvent.change(screen.getByLabelText('Case file'), { target: { value: '20' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Analyze PCAP locally' }));
		await waitFor(() =>
			expect(EvidenceAnalysisService.start).toHaveBeenCalledWith(1, { kind: 'pcap', file_id: 20 })
		);
	});
	it('shows saved partial evidence and permits explicit continuation after failure', async () => {
		const failed = {
			...job,
			status: 'failed',
			error: 'Provider unavailable',
			result: { ...job.result, summary: 'Saved checkpoint' }
		};
		vi.mocked(EvidenceAnalysisService.get).mockResolvedValue(reply(failed));
		vi.mocked(EvidenceAnalysisService.resume).mockResolvedValue(
			reply({ ...failed, status: 'queued' })
		);
		render(AnalysisPage);
		await waitFor(() => expect(screen.getByText('Saved checkpoint')).toBeTruthy());
		await fireEvent.click(screen.getByRole('button', { name: 'Continue analysis' }));
		await waitFor(() => expect(EvidenceAnalysisService.resume).toHaveBeenCalledWith(1, 10));
	});
});
