import russian from './ru.json';

export type Locale = 'en' | 'ru';
export const normalizeLocale = (value: unknown): Locale => value === 'ru' ? 'ru' : 'en';
const catalog: Record<string, string> = russian;

export function translate(source: string, locale: Locale): string {
  if (locale === 'en') return source;
  return catalog[source] || source;
}
