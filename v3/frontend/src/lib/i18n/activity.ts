import { translate, type Locale } from './translate';

// Translate only audit actions; preserve the user-authored resource name.
const actions = ['Created', 'Updated', 'Deleted', 'Added', 'Removed'];
const resources = ['note', 'war room', 'case', 'task', 'asset', 'IOC'];

export function translateActivity(source: string, locale: Locale): string {
	if (locale === 'en') return source;
	const lower = source.toLowerCase();
	for (const action of actions) {
		for (const resource of resources) {
			const prefix = `${action} ${resource}`;
			if (
				lower === prefix.toLowerCase() ||
				lower.startsWith(`${prefix.toLowerCase()} `) ||
				lower.startsWith(`${prefix.toLowerCase()}:`)
			) {
				return translate(`${prefix}{detail}`, locale, { detail: source.slice(prefix.length) });
			}
		}
	}
	return source;
}
