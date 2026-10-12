import { getContext, setContext } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import { normalizeLocale, type Locale } from './translate';
export { translate } from './translate';

const key = Symbol('iris-ui-locale');

export function initLocale(value: unknown): Writable<Locale> {
  const locale = writable(normalizeLocale(value));
  setContext(key, locale);
  return locale;
}

export function useLocale(): Writable<Locale> {
  return getContext<Writable<Locale>>(key) ?? writable('en');
}
