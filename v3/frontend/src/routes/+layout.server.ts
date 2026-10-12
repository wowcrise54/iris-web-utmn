import { normalizeLocale } from '$lib/i18n/translate';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ cookies }) => ({
  locale: normalizeLocale(cookies.get('iris_ui_locale'))
});
