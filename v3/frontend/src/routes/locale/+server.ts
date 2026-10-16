import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { isRequestOriginAllowed, parseAllowedOrigins } from '$lib/config/origins';

const allowedOrigins = parseAllowedOrigins(env.IRIS_ALLOW_ORIGIN);

export const POST: RequestHandler = async ({ request, cookies, url }) => {
	if (!isRequestOriginAllowed(request.headers.get('origin'), url.origin, allowedOrigins)) {
		error(403, 'Invalid origin');
	}
	const { locale } = await request.json();
	if (locale !== 'en' && locale !== 'ru') error(400, 'Unsupported locale');
	cookies.set('iris_ui_locale', locale, {
		path: '/',
		maxAge: 60 * 60 * 24 * 365,
		httpOnly: true,
		sameSite: 'lax',
		secure: url.protocol === 'https:'
	});
	return json({ locale });
};
