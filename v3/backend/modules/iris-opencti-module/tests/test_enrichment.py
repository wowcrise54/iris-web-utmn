from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import unittest
import threading
import time

from iris_opencti_module.client import OpenCTIError
from iris_opencti_module.enrichment import enrich_iocs


class Store:
    def __init__(self):
        self.enabled = True
        self.results = {}
    def active(self):
        return self.enabled
    def scope(self, ioc):
        return [1]
    def lock(self, key):
        return nullcontext()
    def cached(self, key, since):
        return next((deepcopy(r) for r in self.results.values() if r.get('cache_key') == key and r['checked_at'] > since), None)
    def save(self, ioc, result):
        self.results[ioc.ioc_id] = deepcopy(result)
        ioc.ioc_enrichment = {**(ioc.ioc_enrichment or {}), 'opencti': deepcopy(result)}


def ioc(identifier, value='example.org', kind='domain'):
    return SimpleNamespace(ioc_id=identifier, ioc_value=value, ioc_type=SimpleNamespace(type_name=kind), ioc_enrichment={'vt': {'score': 1}})


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.calls = []
        self.client = SimpleNamespace(url='https://cti.example', token='secret', lookup=self.lookup)
    def lookup(self, kind, value):
        self.calls.append((kind, value))
        return {'status': 'no_match', 'observables': [], 'indicators': [], 'relationships': []}

    def test_duplicate_iocs_share_lookup_and_preserve_other_provider(self):
        first, second = ioc(1), ioc(2, 'EXAMPLE.ORG')
        enrich_iocs([first, second], self.store, self.client)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(first.ioc_enrichment['vt'], {'score': 1})
        self.assertEqual(first.ioc_value, 'example.org')
        self.assertEqual(second.ioc_enrichment['opencti']['status'], 'no_match')

    def test_cache_reused_and_manual_refresh_queries_again(self):
        item = ioc(1)
        enrich_iocs([item], self.store, self.client)
        enrich_iocs([item], self.store, self.client)
        self.assertEqual(len(self.calls), 1)
        enrich_iocs([item], self.store, self.client, force=True)
        self.assertEqual(len(self.calls), 2)

    def test_disabled_queued_task_has_no_effect(self):
        self.store.enabled = False
        enrich_iocs([ioc(1)], self.store, self.client)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.results, {})

    def test_disabling_during_request_discards_the_result(self):
        def lookup(*args):
            self.store.enabled = False
            return {'status': 'matched', 'observables': [], 'indicators': []}
        self.client.lookup = lookup
        enrich_iocs([ioc(1)], self.store, self.client)
        self.assertEqual(self.store.results, {})

    def test_unsupported_ioc_is_saved_without_request(self):
        item = ioc(1, 'example.org|1.2.3.4', 'domain|ip')
        enrich_iocs([item], self.store, self.client)
        self.assertEqual(self.calls, [])
        self.assertEqual(item.ioc_enrichment['opencti']['status'], 'unsupported')

    def test_remote_failure_is_result_not_exception_and_not_cached(self):
        self.client.lookup = lambda *args: (_ for _ in ()).throw(OpenCTIError('timeout'))
        item = ioc(1)
        enrich_iocs([item], self.store, self.client)
        self.assertEqual(item.ioc_enrichment['opencti']['status'], 'timeout')
        self.client.lookup = self.lookup
        enrich_iocs([item], self.store, self.client)
        self.assertEqual(len(self.calls), 1)

    def test_different_source_credentials_do_not_reuse_cache(self):
        item = ioc(1)
        enrich_iocs([item], self.store, self.client)
        self.client.token = 'another-secret'
        enrich_iocs([item], self.store, self.client)
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn('secret', str(self.store.results))

    def test_failed_duplicate_values_are_queried_once_per_batch(self):
        def fail(*args):
            self.calls.append(args)
            raise OpenCTIError('timeout')
        self.client.lookup = fail
        enrich_iocs([ioc(1), ioc(2)], self.store, self.client)
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_manual_runs_reuse_result_completed_after_start(self):
        lock = threading.Lock()
        started = threading.Event()
        release = threading.Event()
        self.store.lock = lambda key: lock
        def lookup(*args):
            self.calls.append(args)
            started.set()
            release.wait(2)
            return {'status': 'no_match', 'observables': [], 'indicators': []}
        self.client.lookup = lookup
        failures = []
        def run(item):
            try:
                enrich_iocs([item], self.store, self.client, force=True)
            except Exception as error:
                failures.append(error)
        first = threading.Thread(target=run, args=(ioc(1),))
        second = threading.Thread(target=run, args=(ioc(2),))
        first.start()
        self.assertTrue(started.wait(1))
        second.start()
        time.sleep(0.02)
        release.set()
        first.join(2)
        second.join(2)
        self.assertEqual(failures, [])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.store.results), 2)

    def test_logs_results_cache_and_sanitized_failure(self):
        with self.assertLogs('iris_opencti_module', level='DEBUG') as captured:
            enrich_iocs([ioc(1), ioc(2)], self.store, self.client)
            enrich_iocs([ioc(1)], self.store, self.client)
            self.client.lookup = lambda *args: (_ for _ in ()).throw(OpenCTIError('timeout'))
            enrich_iocs([ioc(3, 'private.example')], self.store, self.client)
        output = '\n'.join(captured.output)
        for expected in ('batch_started', 'batch_completed', 'ioc_id=1', 'cache=batch', 'cache=persistent', 'status=timeout', 'duration_ms='):
            self.assertIn(expected, output)
        for private in ('secret', 'example.org', 'private.example', 'https://cti.example'):
            self.assertNotIn(private, output)

    def test_save_failure_is_logged_and_propagated_without_exception_text(self):
        self.store.save = lambda *args: (_ for _ in ()).throw(RuntimeError('secret private.example'))
        with self.assertLogs('iris_opencti_module', level='ERROR') as captured:
            with self.assertRaises(RuntimeError):
                enrich_iocs([ioc(1)], self.store, self.client)
        self.assertIn('ioc_id=1', str(captured.output))
        self.assertNotIn('private.example', str(captured.output))
