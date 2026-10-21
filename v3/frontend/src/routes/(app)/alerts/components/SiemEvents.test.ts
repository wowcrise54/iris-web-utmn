import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import SiemEvents from './SiemEvents.svelte';

vi.mock('$lib/services/siem-events.service', () => ({ SiemEventsService: { list: vi.fn() } }));
import { SiemEventsService } from '$lib/services/siem-events.service';

const page = (key: string, offset: number, next: number | null) => ({
	ok: true,
	status: 200,
	data: {
		status: 'success',
		data: {
			data: [{ event_key: key, event: { message: `${key} full payload` } }],
			offset,
			next_offset: next,
			has_more: next !== null,
			total: 3,
			limit: 25
		}
	}
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('SIEM events', () => {
	it('loads only on explicit open and replaces the page using the server cursor', async () => {
		vi.mocked(SiemEventsService.list).mockResolvedValueOnce(page('first', 0, 1));
		vi.mocked(SiemEventsService.list).mockResolvedValueOnce(page('second', 1, null));
		render(SiemEvents, { alertId: 42 });
		expect(SiemEventsService.list).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Show SIEM events' }));
		await screen.findByText('first');
		await fireEvent.click(screen.getByText('first'));
		expect(screen.getByText(/first full payload/)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Next' }));
		await screen.findByText('second');
		expect(screen.queryByText('first')).toBeNull();
		expect(SiemEventsService.list).toHaveBeenLastCalledWith(
			42,
			1,
			expect.objectContaining({ signal: expect.any(AbortSignal) })
		);
		expect(screen.getByRole('button', { name: 'Next' }).hasAttribute('disabled')).toBe(true);
	});

	it('cancels pending requests and discards stale results when the alert changes', async () => {
		let resolve!: (value: ReturnType<typeof page>) => void;
		vi.mocked(SiemEventsService.list).mockImplementationOnce(
			() =>
				new Promise((r) => {
					resolve = r;
				})
		);
		const view = render(SiemEvents, { alertId: 42 });
		await fireEvent.click(screen.getByRole('button', { name: 'Show SIEM events' }));
		const options = vi.mocked(SiemEventsService.list).mock.calls[0][2];
		await view.rerender({ alertId: 43 });
		expect(options?.signal?.aborted).toBe(true);
		resolve(page('stale', 0, null));
		await waitFor(() =>
			expect(screen.getByRole('button', { name: 'Show SIEM events' })).toBeTruthy()
		);
		expect(screen.queryByText('stale')).toBeNull();
	});

	it('shows a fetch error with an explicit retry', async () => {
		vi.mocked(SiemEventsService.list).mockResolvedValueOnce({ ok: false, status: 500, data: null });
		vi.mocked(SiemEventsService.list).mockResolvedValueOnce(page('retried', 0, null));
		render(SiemEvents, { alertId: 42 });
		await fireEvent.click(screen.getByRole('button', { name: 'Show SIEM events' }));
		await screen.findByRole('alert');
		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
		await screen.findByText('retried');
	});
});
