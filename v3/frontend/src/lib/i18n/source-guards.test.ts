import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parse } from 'svelte/compiler';

const srcRoot = join(process.cwd(), 'src');

function svelteFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		return entry.isDirectory() ? svelteFiles(path) : entry.name.endsWith('.svelte') ? [path] : [];
	});
}

function hasUntranslatedText(node: any): boolean {
	if (!node || typeof node !== 'object') return false;
	if (node.type === 'CallExpression' && node.callee?.name === 'irisT') return false;
	if (node.type === 'Text') return /[A-Za-z]/.test(node.data);
	if (node.type === 'Literal' && typeof node.value === 'string') return /[A-Za-z]/.test(node.value);
	if (node.type === 'TemplateElement') return /[A-Za-z]/.test(node.value.cooked ?? '');
	// Conditions and computed property names are identifiers, not displayed text.
	if (node.type === 'MemberExpression') return hasUntranslatedText(node.object);
	if (node.type === 'ConditionalExpression') {
		return hasUntranslatedText(node.consequent) || hasUntranslatedText(node.alternate);
	}
	return Object.values(node).some(hasUntranslatedText);
}

function untranslatedNodes(kind: 'title' | 'message' | 'aria-label' | 'ariaLabel'): string[] {
	const failures: string[] = [];
	for (const file of svelteFiles(srcRoot)) {
		const source = readFileSync(file, 'utf8');
		if (kind === 'title' ? !/<title(?:\s|>)/.test(source) : !source.includes(kind)) continue;
		const visit = (node: any) => {
			if (!node || typeof node !== 'object') return;
			if (node.name === kind && (kind === 'title' || node.type === 'Attribute')) {
				if (hasUntranslatedText(kind === 'title' ? node.children : node.value)) {
					failures.push(`${relative(srcRoot, file)}: ${source.slice(node.start, node.end).trim()}`);
				}
			}
			Object.values(node).forEach(visit);
		};
		visit(parse(source).html);
	}
	return failures;
}

describe('localization source guards', () => {
	it('catches an untranslated fragment even when another fragment uses irisT', () => {
		const check = (title: string) => hasUntranslatedText(parse(`<title>${title}</title>`).html);
		expect(check('Dashboard {irisT("Settings", locale)}')).toBe(true);
		expect(check('{name ?? "Dashboard"} {irisT("Settings", locale)}')).toBe(true);
		expect(check('{name} — {irisT("Settings", locale)}')).toBe(false);
	});
	it('routes every static page title fragment through irisT', () => {
		expect(untranslatedNodes('title')).toEqual([]);
	});
	it('routes static confirmation message fragments through irisT', () => {
		expect(untranslatedNodes('message')).toEqual([]);
	});
	it('routes static aria label fragments through irisT while allowing data-only labels', () => {
		expect([...untranslatedNodes('aria-label'), ...untranslatedNodes('ariaLabel')]).toEqual([]);
	});
	it('describes every selected ID even when its alert object is missing from the cache', () => {
		const source = readFileSync(join(srcRoot, 'routes/(app)/alerts/+page.svelte'), 'utf8');
		const findDialog = (node: any): any => {
			if (!node || typeof node !== 'object') return undefined;
			if (node.name === 'ConfirmationDialog' && node.attributes?.some((attribute: any) =>
				attribute.type === 'Binding' && attribute.expression?.name === 'showConfirmDelete')) return node;
			return Object.values(node).map(findDialog).find(Boolean);
		};
		const dialog = findDialog(parse(source).html);
		const expression = dialog.attributes.find((attribute: any) => attribute.name === 'message').value[0].expression;
		const render = new Function('getSelectedCount', 'getSelectedAlerts', 'irisT', '$irisLocale',
			`return (${source.slice(expression.start, expression.end)});`);
		expect(render(() => 2, () => [{}], (text: string) => text, 'en')).toContain('selected alerts');
		expect(render(() => 1, () => [], (text: string) => text, 'en')).toContain('selected alert and');
	});
});
