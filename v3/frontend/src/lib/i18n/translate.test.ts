import { describe, it, expect } from 'vitest';
import { translate, normalizeLocale } from './translate';

describe('IRIS localization', () => {
	it('interpolates user values verbatim after translating the message template', () => {
		expect(
			translate('Delete rule "{name}"? This cannot be undone.', 'en', { name: '$& {name}' })
		).toBe('Delete rule "$& {name}"? This cannot be undone.');
		expect(translate('Delete rule "{name}"? This cannot be undone.', 'ru', { name: 'Save' })).toBe(
			'Удалить правило «Save»? Это действие нельзя отменить.'
		);
		expect(translate('Count: {count}', 'en', { count: 0 })).toBe('Count: 0');
	});
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

	it('uses the established Russian action and workflow terminology', () => {
		expect(translate('Import case', 'ru')).toBe('Импорт инцидента');
		expect(translate('Resolve', 'ru')).toBe('Сопоставление');
		expect(translate('Escalate', 'ru')).toBe('Эскалировать');
		expect(translate('Review', 'ru')).toBe('Проверка');
		expect(translate('Archive', 'ru')).toBe('Архивировать');
		expect(translate('Filter by', 'ru')).toBe('Фильтровать по');
	});
});
