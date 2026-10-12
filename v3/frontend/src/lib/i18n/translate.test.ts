import { describe, it, expect } from 'vitest';
import { translate, normalizeLocale } from './translate';

describe('IRIS localization', () => {
  it('keeps English as the default and rejects unknown locales', () => {
    expect(normalizeLocale(undefined)).toBe('en');
    expect(normalizeLocale('invalid')).toBe('en');
    expect(normalizeLocale('ru')).toBe('ru');
    expect(translate('Save', 'en')).toBe('Save');
  });
  it('translates known interface labels and preserves user content', () => {
    expect(translate('Save', 'ru')).toBe('Сохранить');
    expect(translate('My own incident title №2', 'ru')).toBe('My own incident title №2');
  });
  it('isolates language selection between requests', () => {
    expect(translate('Save', 'ru')).toBe('Сохранить');
    expect(translate('Save', 'en')).toBe('Save');
  });
});
