const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const alertsPath = path.resolve(
    __dirname,
    '../../../app/static/assets/js/iris/alerts.js',
);
const alertsSource = fs.readFileSync(alertsPath, 'utf8');
const rendererStart = alertsSource.indexOf('function encodeEnrichmentData');
const rendererEnd = alertsSource.indexOf('function delete_alert', rendererStart);

assert(rendererStart >= 0 && rendererEnd > rendererStart, 'OpenCTI renderer functions not found');

const context = {
    URL,
    window: {location: {origin: 'https://iris.local'}},
    filterXSS: (value) => String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;'),
    btoa,
    atob,
    escape,
    unescape,
    encodeURIComponent,
    decodeURIComponent,
    console,
};
vm.createContext(context);
vm.runInContext(alertsSource.slice(rendererStart, rendererEnd), context);

const baseMatch = {
    id: 'indicator--1',
    source: 'indicator',
    entity_type: 'Indicator',
    value: 'example.com',
    iris_ioc_type: 'domain',
    score: 80,
    confidence: 90,
    labels: ['phishing', '<img src=x onerror=alert(1)>'],
    markings: ['TLP:AMBER'],
    external_references: [
        {source_name: 'unsafe', url: 'javascript:alert(1)'},
        {source_name: 'safe', url: 'https://example.com/reference'},
    ],
    related_entities: [{
        id: 'malware--1',
        entity_type: 'Malware',
        name: 'Mimikatz',
        relationship_type: 'indicates',
        opencti_url: 'https://opencti.local/dashboard/id/malware--1',
    }],
    opencti_url: 'https://opencti.local/dashboard/id/indicator--1',
};
const duplicateObservable = {
    ...baseMatch,
    id: 'observable--1',
    source: 'observable',
    entity_type: 'Domain-Name',
};

const matchHtml = context.renderOpenCTIEnrichment({
    status: 'match',
    match_count: 2,
    last_success_utc: '2026-07-29T00:00:00Z',
    matches: [baseMatch, duplicateObservable],
});
assert(matchHtml.includes('Найдено точных объектов: 2'));
assert(matchHtml.includes('Mimikatz'));
assert(matchHtml.includes('&lt;img src=x onerror=alert(1)&gt;'));
assert(!matchHtml.includes('javascript:'));
assert.strictEqual((matchHtml.match(/<div class="card mb-3">/g) || []).length, 1);

const noMatchHtml = context.renderOpenCTIEnrichment({
    status: 'no_match',
    match_count: 0,
    matches: [],
});
assert(noMatchHtml.includes('Точных совпадений в OpenCTI не найдено'));

const errorHtml = context.renderOpenCTIEnrichment({
    status: 'error',
    error: '<connection failed>',
    last_success_utc: '2026-07-29T00:00:00Z',
    matches: [baseMatch],
});
assert(errorHtml.includes('Последняя попытка завершилась ошибкой'));
assert(errorHtml.includes('&lt;connection failed&gt;'));
assert(errorHtml.includes('Показан последний успешный результат'));

const summaryHtml = context.renderOpenCTIAlertSummary([
    {ioc_enrichment: {opencti: {status: 'match'}}},
    {ioc_enrichment: {opencti: {status: 'no_match'}}},
    {ioc_enrichment: {opencti: {status: 'error'}}},
]);
assert(summaryHtml.includes('Проверено: 3'));
assert(summaryHtml.includes('Найдено: 1'));
assert(summaryHtml.includes('Без совпадений: 1'));
assert(summaryHtml.includes('Ошибки: 1'));

console.log('OpenCTI alert UI renderer tests passed');
