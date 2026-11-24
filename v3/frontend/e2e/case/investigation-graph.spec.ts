import { randomUUID } from 'node:crypto';
import { test, expect } from '../helpers/fixtures';
import { login } from '../helpers/auth';
import { adminApi, apiJson, cleanup, seed } from '../helpers/api';

test('case graph pushes edits and records a supporting timeline event', async ({
	page,
	browser
}, testInfo) => {
	test.setTimeout(90_000);
	const api = await adminApi();
	const caseId = await seed.case(api, { case_name: 'e2e investigation graph' });
	const graphUrl = `/api/v2/cases/${caseId}/graph`;
	const observerContext = await browser.newContext({
		baseURL: testInfo.project.use.baseURL,
		ignoreHTTPSErrors: true
	});
	const observer = await observerContext.newPage();
	let viewerId: number | undefined;
	let viewerGroupId: number | undefined;
	const received: string[] = [];
	observer.on('websocket', (socket) => {
		socket.on('framereceived', ({ payload }) => received.push(payload.toString()));
	});

	try {
		const viewerLogin = 'graph-viewer-' + randomUUID();
		const viewerPassword = 'Aa1!' + randomUUID();
		const viewerName = 'Graph observer';
		const users = '/api/v2/manage/users';
		const groups = '/api/v2/manage/groups';
		const user = await api.post(users, {
			data: {
				user_name: viewerName,
				user_login: viewerLogin,
				user_email: viewerLogin + '@example.invalid',
				user_password: viewerPassword,
				user_active: true,
				user_isadmin: false
			}
		});
		expect(user.ok(), await user.text()).toBeTruthy();
		viewerId = (await apiJson<{ user_id: number }>(user)).user_id;
		const group = await api.post(groups, {
			data: {
				group_name: viewerLogin,
				group_description: 'Graph read-only e2e fixture',
				group_permissions: 1
			}
		});
		expect(group.ok(), await group.text()).toBeTruthy();
		viewerGroupId = (await apiJson<{ group_id: number }>(group)).group_id;
		const membership = await api.put(`${groups}/${viewerGroupId}/members`, {
			data: { members: [viewerId] }
		});
		expect(membership.ok(), await membership.text()).toBeTruthy();
		const grant = await api.post(`${users}/${viewerId}/cases-access`, {
			data: { cases_list: [caseId], access_level: 2 }
		});
		expect(grant.ok(), await grant.text()).toBeTruthy();
		await login(page);
		const createNode = async (label: string) => {
			const response = await api.post(`${graphUrl}/nodes`, { data: { label } });
			expect(response.ok(), await response.text()).toBeTruthy();
			return apiJson<{ key: string }>(response);
		};
		const source = await createNode('Graph e2e source');
		const target = await createNode('Graph e2e target');
		const viewState = { positions: {}, center: { x: 0, y: 0 }, scale: 1 };
		for (const shared of [false, true]) {
			const view = await api.post(`${graphUrl}/views`, {
				data: {
					label: shared ? 'Shared e2e view' : 'Private e2e view',
					state: viewState,
					is_shared: shared
				}
			});
			expect(view.ok(), await view.text()).toBeTruthy();
		}
		await login(observer, viewerLogin, viewerPassword);
		await observer.goto(`/case/${caseId}/graph`);
		await expect(observer.getByText(/^(Graph viewers|Смотрят граф)/)).toBeVisible();
		const viewerViews = observer.getByRole('combobox', {
			name: /Saved graph views|Сохранённые представления/
		});
		await expect(viewerViews.getByRole('option', { name: /Shared e2e view/ })).toHaveCount(1);
		await expect(viewerViews.getByRole('option', { name: /Private e2e view/ })).toHaveCount(0);
		await expect(
			observer.getByRole('button', { name: /^(Add graph node|Добавить узел графа)$/ })
		).toHaveCount(0);
		await page.goto(`/case/${caseId}/graph`);
		await expect(page.getByText(/^(Graph viewers|Смотрят граф).*Graph observer/)).toBeVisible({
			timeout: 15_000
		});
		const response = await api.post(`${graphUrl}/edges`, {
			data: {
				source: source.key,
				target: target.key,
				label: 'Graph e2e connection',
				directed: true,
				relation: 'related_to'
			}
		});
		expect(response.ok(), await response.text()).toBeTruthy();
		const edge = await apiJson<{ id: number; key: string }>(response);
		await expect.poll(() => received.some((frame) => frame.includes('graph-changed'))).toBe(true);
		const edgeSelect = observer.getByRole('combobox', {
			name: /Select a connection|Выберите связь/
		});
		await expect(edgeSelect.getByRole('option', { name: /Graph e2e connection/ })).toHaveCount(1);

		const editorSelect = page.getByRole('combobox', { name: /Select a connection|Выберите связь/ });
		await expect(editorSelect.getByRole('option', { name: /Graph e2e connection/ })).toHaveCount(1);
		await editorSelect.selectOption(edge.key);
		await page.getByText(/^(Record supporting event|Создать подтверждающее событие)$/).click();
		await page.getByLabel(/Event title|Заголовок события/).fill('Graph e2e supporting event');
		await page
			.getByLabel(/Event time \(local\)|Время события \(местное\)/)
			.fill('2026-11-24T10:00');

		const saved = page.waitForResponse(
			(res) =>
				res.url().endsWith(`${graphUrl}/edges/${edge.id}/events`) &&
				res.request().method() === 'POST'
		);
		await page
			.locator('details[open]')
			.getByRole('button', { name: /^(Save|Сохранить)$/ })
			.click();
		const eventResponse = await saved;
		expect(eventResponse.ok(), await eventResponse.text()).toBeTruthy();
		const event = await apiJson<{ id: number }>(eventResponse);
		const link = page.getByRole('link', { name: /Graph e2e supporting event/ });
		await expect(link).toHaveAttribute('href', `/case/${caseId}/timeline?event=${event.id}`);
		await link.click();
		await expect(page).toHaveURL(new RegExp(`/case/${caseId}/timeline\\?event=${event.id}`), {
			timeout: 20_000
		});
		await expect
			.poll(async () => {
				const detail = await api.get(`/api/v2/cases/${caseId}/events/${event.id}`);
				const data = await apiJson<{ timeline_ids?: number[] }>(detail);
				return data.timeline_ids?.length ?? 0;
			})
			.toBeGreaterThan(0);
	} finally {
		await observerContext.close();
		await cleanup.case(api, caseId);
		if (viewerGroupId) await api.delete(`/api/v2/manage/groups/${viewerGroupId}`);
		if (viewerId) await api.delete(`/api/v2/manage/users/${viewerId}`);
		await api.dispose();
	}
});

test('case graph saves a shared PNG and selects it for reports', async ({ page }) => {
	test.setTimeout(60_000);
	const api = await adminApi();
	const caseId = await seed.case(api, { case_name: 'e2e investigation graph view' });
	const graphUrl = `/api/v2/cases/${caseId}/graph`;
	try {
		const node = await api.post(`${graphUrl}/nodes`, { data: { label: 'Graph snapshot node' } });
		expect(node.ok(), await node.text()).toBeTruthy();
		await login(page);
		await page.goto(`/case/${caseId}/graph`);
		await page
			.getByRole('button', { name: /^(Save graph view|Сохранить представление графа)$/ })
			.click();
		const dialog = page.getByRole('dialog');
		await dialog.getByRole('textbox', { name: /^(Name|Название)$/ }).fill('Graph e2e report view');
		await dialog
			.getByRole('checkbox', { name: /Share with case members|Открыть участникам кейса/ })
			.check();
		await dialog
			.getByRole('checkbox', { name: /Save a PNG snapshot|Сохранить снимок PNG/ })
			.check();
		await dialog
			.getByRole('checkbox', {
				name: /Use this view in investigation reports|Использовать это представление в отчётах/
			})
			.check();
		const posted = page.waitForResponse(
			(res) => res.url().endsWith(`${graphUrl}/views`) && res.request().method() === 'POST'
		);
		await dialog.getByRole('button', { name: /^(Save|Сохранить)$/ }).click();
		const response = await posted;
		expect(response.ok(), await response.text()).toBeTruthy();
		const view = await apiJson<{
			id: number;
			is_shared: boolean;
			has_snapshot: boolean;
			is_report_default: boolean;
		}>(response);
		expect(view).toMatchObject({ is_shared: true, has_snapshot: true, is_report_default: true });
		const snapshots = page.getByRole('combobox', {
			name: /Saved graph views|Сохранённые представления/
		});
		await expect(snapshots.getByRole('option', { name: /Graph e2e report view/ })).toHaveCount(1);
		await snapshots.selectOption(String(view.id));
		const download = page.waitForEvent('download');
		await page
			.getByRole('button', { name: /Download saved graph snapshot|Скачать сохранённый снимок/ })
			.click();
		const file = await download;
		expect(file.suggestedFilename()).toBe(`case-${caseId}-graph-view-${view.id}.png`);
		expect(await file.failure()).toBeNull();
	} finally {
		await cleanup.case(api, caseId);
		await api.dispose();
	}
});
