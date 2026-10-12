import russian from './ru.json';

export type Locale = 'en' | 'ru';
export const normalizeLocale = (value: unknown): Locale => (value === 'ru' ? 'ru' : 'en');
const catalog: Record<string, string> = russian;

export function translate(
	source: string,
	locale: Locale,
	values?: Record<string, string | number>
): string {
	const message = locale === 'en' ? source : catalog[source] || source;
	if (!values) return message;
	return message.replace(/\{(\w+)\}/g, (placeholder, key: string) =>
		Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : placeholder
	);
}
