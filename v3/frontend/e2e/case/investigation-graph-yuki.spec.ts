import { createServer } from 'node:http';
import { test, expect } from '../helpers/fixtures';
import { login } from '../helpers/auth';
import { adminApi, apiJson, cleanup, seed } from '../helpers/api';

test('Yuki reads graph evidence through MCP and applies a reviewed link', async ({ page }) => {
	test.skip(process.env.GRAPH_YUKI_CHECK !== '1', 'Uses an isolated server settings fixture.');
	test.setTimeout(100_000);
	const api = await adminApi();
	const caseId = await seed.case(api, { case_name: 'e2e Yuki graph suggestions' });
	const graphUrl = `/api/v2/cases/${caseId}/graph`;
	const settingsUrl = '/api/v2/manage/server/settings';
	const fixtureSettings = {
		chatbot_enabled: true,
		chatbot_provider: 'custom',
		chatbot_model: 'graph-e2e',
		chatbot_base_url: ''
	};
	let previousSettings: Record<string, unknown> | undefined;
	let proposal: Array<Record<string, unknown>> = [];
	let sawMcpResults = false;
	let providerError: string | undefined;
	const provider = createServer(async (request, response) => {
		try {
			if (!request.url?.endsWith('/chat/completions')) {
				response.writeHead(404).end();
				return;
			}
			const chunks: Buffer[] = [];
			for await (const chunk of request) chunks.push(Buffer.from(chunk));
			const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
			const frames: object[] = [];
			const results = body.messages.filter((message: { role: string }) => message.role === 'tool');
			if (!results.length) {
				if (
					!body.tools.some(
						(tool: { function: { name: string } }) => tool.function.name === 'iris_case_graph_get'
					)
				)
					throw new Error('Graph MCP tool was missing from the provider request');
				const tool_calls = ['nodes', 'edges', 'events'].map((section, index) => ({
					index,
					id: 'graph-' + section,
					type: 'function',
					function: { name: 'iris_case_graph_get', arguments: JSON.stringify({ section }) }
				}));
				frames.push({ choices: [{ delta: { tool_calls }, finish_reason: null }] });
				frames.push({ choices: [{ delta: {}, finish_reason: 'tool_calls' }] });
			} else {
				const toolData = results.map((row: { content: string }) => row.content).join('\n');
				if (
					!['Graph source for Yuki', 'event_count', 'Graph evidence for Yuki'].every((marker) =>
						toolData.includes(marker)
					)
				)
					throw new Error('MCP did not return the expected graph fixtures');
				sawMcpResults = true;
				frames.push({
					choices: [{ delta: { content: JSON.stringify(proposal) }, finish_reason: 'stop' }]
				});
			}
			response.writeHead(200, { 'Content-Type': 'text/event-stream' });
			response.end(
				frames.map((frame) => 'data: ' + JSON.stringify(frame) + '\n\n').join('') +
					'data: [DONE]\n\n'
			);
		} catch (error) {
			providerError = String(error);
			response.writeHead(500).end();
		}
	});
	try {
		await new Promise<void>((resolve, reject) => {
			provider.once('error', reject);
			provider.listen(0, '127.0.0.1', resolve);
		});
		const address = provider.address();
		if (!address || typeof address === 'string') throw new Error('Provider did not bind to TCP');
		fixtureSettings.chatbot_base_url = `http://127.0.0.1:${address.port}/v1`;
		previousSettings = await apiJson<Record<string, unknown>>(await api.get(settingsUrl));
		const configuration = await api.put(settingsUrl, { data: fixtureSettings });
		expect(configuration.ok(), await configuration.text()).toBeTruthy();

		const create = async <T>(path: string, data: object) => {
			const response = await api.post(path, { data });
			expect(response.ok(), await response.text()).toBeTruthy();
			return apiJson<T>(response);
		};
		const from = await create<{ key: string }>(graphUrl + '/nodes', {
			label: 'Graph source for Yuki'
		});
		const known = await create<{ key: string }>(graphUrl + '/nodes', {
			label: 'Graph observed target'
		});
		const target = await create<{ key: string }>(graphUrl + '/nodes', {
			label: 'Graph suggested target'
		});
		const edge = await create<{ id: number }>(graphUrl + '/edges', {
			source: from.key,
			target: known.key,
			label: 'Graph observed link',
			relation: 'related_to',
			directed: true
		});
		const event = await create<{ id: number }>(`${graphUrl}/edges/${edge.id}/events`, {
			title: 'Graph evidence for Yuki',
			occurred_at: '2026-11-24T11:00:00Z'
		});
		proposal = [
			{
				source: from.key,
				target: target.key,
				relation: 'related_to',
				directed: true,
				event_ids: [event.id],
				rationale: 'Synthetic evidence supports the proposed connection.'
			}
		];

		await login(page);
		await page.goto(`/case/${caseId}/graph`);
		await page
			.getByRole('button', { name: /Graph link suggestions|Предложить связи с Yuki/ })
			.click();
		const review = page.getByRole('button', {
			name: /Review proposed connection|Рассмотреть связь/
		});
		await expect(review, providerError).toBeVisible({ timeout: 35_000 });
		expect(providerError).toBeUndefined();
		expect(sawMcpResults).toBe(true);
		const beforeReview = await apiJson<{ edges: Array<Record<string, unknown>> }>(
			await api.get(graphUrl)
		);
		expect(beforeReview.edges).not.toContainEqual(
			expect.objectContaining({ source: from.key, target: target.key })
		);
		await review.click();
		const dialog = page.getByRole('dialog');
		const saved = page.waitForResponse(
			(res) => res.url().endsWith(graphUrl + '/edges') && res.request().method() === 'POST'
		);
		await dialog.getByRole('button', { name: /^(Save|Сохранить)$/ }).click();
		const response = await saved;
		expect(response.ok(), await response.text()).toBeTruthy();
		const graph = await apiJson<{ edges: Array<Record<string, unknown>> }>(await api.get(graphUrl));
		expect(graph.edges).toContainEqual(
			expect.objectContaining({
				source: from.key,
				target: target.key,
				event_ids: [event.id]
			})
		);
	} finally {
		provider.closeAllConnections();
		await new Promise<void>((resolve) => provider.close(() => resolve()));
		if (previousSettings) {
			await api.put(settingsUrl, {
				data: Object.fromEntries(
					Object.keys(fixtureSettings).map((field) => [field, previousSettings?.[field]])
				)
			});
		}
		await cleanup.case(api, caseId);
		await api.dispose();
	}
});
