import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, cookies, url }) => {
  if (request.headers.get('origin') !== url.origin) error(403, 'Invalid origin');
  const { locale } = await request.json();
  if (locale !== 'en' && locale !== 'ru') error(400, 'Unsupported locale');
  cookies.set('iris_ui_locale', locale, {
    path: '/', maxAge: 60 * 60 * 24 * 365,
    httpOnly: true, sameSite: 'lax', secure: url.protocol === 'https:'
  });
  return json({ locale });
};
