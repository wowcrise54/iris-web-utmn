// @vitest-environment node
import { beforeEach, expect, it, vi } from 'vitest';
vi.mock('$env/dynamic/private', () => ({
	env: {
		IRIS_ALLOW_ORIGIN: 'https://alternate.example, HTTPS://SECOND.example:443/'
	}
}));
const { POST } = await import('../routes/locale/+server');
const cookies = { set: vi.fn() };
const send = (origin: string | null, locale = 'ru') =>
	POST({
		url: new URL('https://primary.example/locale'),
		cookies,
		request: new Request('https://primary.example/locale', {
			method: 'POST',
			headers: origin === null ? {} : { origin },
			body: JSON.stringify({ locale })
		})
	} as never);
beforeEach(() => cookies.set.mockClear());
it.each(['https://primary.example', 'https://alternate.example', 'https://second.example'])(
	'sets language from a served origin: %s',
	async (origin) => {
		expect((await send(origin)).status).toBe(200);
		expect(cookies.set).toHaveBeenCalledWith(
			'iris_ui_locale',
			'ru',
			expect.objectContaining({ httpOnly: true, secure: true })
		);
	}
);
it.each(['https://evil.example', 'null', null])(
	'rejects unlisted or missing origin: %s',
	async (origin) => {
		await expect(send(origin)).rejects.toMatchObject({ status: 403 });
		expect(cookies.set).not.toHaveBeenCalled();
	}
);
it('rejects unsupported locales before setting a cookie', async () => {
	await expect(send('https://primary.example', 'xx')).rejects.toMatchObject({ status: 400 });
	expect(cookies.set).not.toHaveBeenCalled();
});
