import { expect, it } from 'vitest';
import { translateActivity } from './activity';

it('localizes audit actions while preserving resource names and unknown messages', () => {
	expect(translateActivity('Deleted note "v3 transport $&"', 'ru')).toBe(
		'Удалена заметка "v3 transport $&"'
	);
	expect(translateActivity('Created note: Save', 'ru')).toBe('Создана заметка: Save');
	expect(translateActivity('Deleted note "v3"', 'en')).toBe('Deleted note "v3"');
	expect(translateActivity('deleted note "v3"', 'en')).toBe('deleted note "v3"');
	expect(translateActivity('deleted note "Save"', 'ru')).toBe('Удалена заметка "Save"');
	expect(translateActivity('Custom event', 'ru')).toBe('Custom event');
});
