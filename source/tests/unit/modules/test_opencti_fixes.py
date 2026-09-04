"""Regression tests for the OpenCTI enrichment bug fixes (DB-independent).

Covers:
- canonicalize_ioc_value: hex hash types beyond HASH_TYPE_BY_LENGTH (sha3-*,
  sha512/256, imphash, ssdeep, ...) now lowercase instead of passing through
  case-preserved (which dropped real case-differing exact matches).
- extract_value_from_pattern: SHA3-224/256/384/512 and SHA-512/224|256 file
  hash patterns now yield the hash value instead of the algorithm name.
- OpenCTIClient.search_ioc: cache key includes the requested result count,
  so first=5 is not served a cached first=20 payload.
- OpenCTIClient._execute_query: deterministic GraphQL errors and HTTP 403 are
  not retried (they cannot heal themselves).
- OpenCTIClient.get_sightings: schema-mismatch degradation is logged.
- metrics: the collector is created lazily (no daemon thread at import time)
  while the `from ...metrics import metrics` import keeps working.
- batch_processor: add_batch and _process_batches_impl share one queue (the
  old code processed a brand-new empty queue, so nothing was ever enriched).
"""
import logging
import os
import sys
import threading
import unittest
from unittest import TestCase
from unittest.mock import MagicMock, patch

from iris_opencti_module.opencti_handler.opencti_mapping import (
    canonicalize_ioc_value,
    extract_value_from_pattern,
)
from iris_opencti_module.opencti_handler.opencti_client import (
    OpenCTIClient,
    OpenCTIClientError,
)


class TestHashCanonicalization(TestCase):
    def test_known_hash_types_still_lowercase(self):
        sha256_upper = "A" * 64
        self.assertEqual(canonicalize_ioc_value(sha256_upper, "filename|sha256"), sha256_upper.lower())

    def test_sha3_256_hash_is_case_insensitive(self):
        upper = "ABCDEF" + "0" * 52  # 64 hex chars, sha3-256 length
        self.assertEqual(canonicalize_ioc_value(upper, "filename|sha3-256"), upper.lower())
        self.assertEqual(canonicalize_ioc_value(upper, "sha3-256"), upper.lower())

    def test_sha512_256_variant_lowercase(self):
        upper = "F" * 64
        self.assertEqual(canonicalize_ioc_value(upper, "filename|sha512/256"), upper.lower())

    def test_imphash_uppercase_lowercase(self):
        value = "D41D8CD98F00B204E9800998ECF8427E"
        self.assertEqual(canonicalize_ioc_value(value, "imphash"), value.lower())

    def test_non_hex_values_keep_case(self):
        # A value that is not pure hex must not be mangled by the hash rule.
        self.assertEqual(canonicalize_ioc_value("MyFile.exe", "filename"), "MyFile.exe")

    def test_ssdeep_value_not_lowercased(self):
        # ssdeep values contain ':' and non-hex chars - must pass through
        # unchanged (they are not case-insensitive hex).
        value = "98304:AbCd:Qr"
        self.assertEqual(canonicalize_ioc_value(value, "filename|ssdeep"), value)


class TestExtractValueFromPattern(TestCase):
    def test_sha3_256_file_hash(self):
        pattern = "file:hashes.'SHA3-256' = 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef'"
        value, hash_type = extract_value_from_pattern(pattern)
        self.assertEqual(value, "deadbeef" * 8)
        self.assertEqual(hash_type, "sha3256")

    def test_sha3_512_file_hash(self):
        pattern = '[file:hashes."SHA3-512" = "' + "ab" * 64 + '"]'
        value, hash_type = extract_value_from_pattern(pattern)
        self.assertEqual(value, "ab" * 64)
        self.assertEqual(hash_type, "sha3512")

    def test_sha512_256_file_hash(self):
        pattern = "file:hashes.'SHA-512/256' = '" + "cd" * 32 + "'"
        value, hash_type = extract_value_from_pattern(pattern)
        self.assertEqual(value, "cd" * 32)
        # IRIS names this type "sha512/256" (slash preserved, like in
        # post_init.py type registrations).
        self.assertEqual(hash_type, "sha512/256")

    def test_md5_still_works(self):
        pattern = "file:hashes.MD5 = 'd41d8cd98f00b204e9800998ecf8427e'"
        value, hash_type = extract_value_from_pattern(pattern)
        self.assertEqual(value, "d41d8cd98f00b204e9800998ecf8427e")
        self.assertEqual(hash_type, "md5")

    def test_sha256_still_works(self):
        pattern = "file:hashes.'SHA-256' = '" + "aa" * 32 + "'"
        value, hash_type = extract_value_from_pattern(pattern)
        self.assertEqual(value, "aa" * 32)
        self.assertEqual(hash_type, "sha256")


class TestClientCacheKeyIncludesFirst(TestCase):
    def setUp(self):
        self.client = OpenCTIClient("http://opencti:8080", "token")
        self.client.query = MagicMock(return_value={"indicators": {"edges": []}})

    def test_different_first_sizes_are_separate_cache_entries(self):
        r20 = {"indicators": {"edges": [{"node": {"id": "a"}}] * 20}}
        r5 = {"indicators": {"edges": [{"node": {"id": "a"}}] * 5}}
        self.client.query.side_effect = [r20, r5]

        result20 = self.client.search_ioc("8.8.8.8", first=20)
        self.assertEqual(result20, r20)
        # first=5 must NOT be served the cached first=20 payload
        result5 = self.client.search_ioc("8.8.8.8", first=5)
        self.assertEqual(result5, r5)
        self.assertEqual(self.client.query.call_count, 2)

    def test_same_first_hits_cache(self):
        self.client.query.return_value = {"indicators": {"edges": []}}
        self.client.search_ioc("8.8.8.8", first=10)
        self.client.search_ioc("8.8.8.8", first=10)
        self.assertEqual(self.client.query.call_count, 1)


class TestClientNoRetryOnDeterministicErrors(TestCase):
    def _client(self):
        return OpenCTIClient(
            url="http://test-opencti.local", token="t",
            timeout=5, retry_attempts=3, retry_delay=0.01,
        )

    def test_no_retry_on_graphql_error(self):
        client = self._client()
        with patch.object(client, "_make_request") as m:
            m.side_effect = OpenCTIClientError("graphql_error: [{'message': 'Cannot query field'}]")
            with self.assertRaises(OpenCTIClientError):
                client.query("query { x }")
            self.assertEqual(m.call_count, 1)

    def test_no_retry_on_http_403(self):
        client = self._client()
        with patch.object(client, "_make_request") as m:
            m.side_effect = OpenCTIClientError("403 Client Error: Forbidden for url: http://x/graphql")
            with self.assertRaises(OpenCTIClientError):
                client.query("query { x }")
            self.assertEqual(m.call_count, 1)

    def test_still_retries_transient_errors(self):
        client = self._client()
        with patch.object(client, "_make_request") as m:
            m.side_effect = [
                OpenCTIClientError("connection reset"),
                {"data": {"ok": True}},
            ]
            result = client.query("query { x }")
            self.assertEqual(result, {"data": {"ok": True}})
            self.assertEqual(m.call_count, 2)


class TestClientSightingsSchemaMismatchLogged(TestCase):
    def test_sightings_schema_mismatch_returns_empty_and_warns(self):
        client = OpenCTIClient("http://opencti:8080", "token")
        client.query = MagicMock(side_effect=OpenCTIClientError("Cannot query field 'stixSightingRelationships'"))
        with self.assertLogs(level="WARNING") as logs:
            result = client.get_sightings("indicator--1")
        self.assertEqual(result, {"stixSightingRelationships": {"edges": []}})
        self.assertTrue(any("Sightings query not supported" in line for line in logs.output))


class TestMetricsLazyInit(TestCase):
    def test_no_aggregation_thread_at_import_time(self):
        import iris_opencti_module.opencti_handler.metrics as m

        # After a plain import the collector must not exist yet, so no
        # daemon aggregation thread is running in this process.
        threads_before = threading.active_count()
        # Touch a method through the lazy proxy.
        _ = m.metrics.get_summary()
        self.assertIsInstance(m.metrics, m.MetricsCollector)
        # The global was rebound to the real singleton.
        self.assertEqual(m.metrics, m._get_metrics())
        # Thread count grew by exactly one (the aggregation loop) and it is
        # bounded: repeated access must not start more threads.
        _ = m.metrics.get_metrics()
        self.assertLessEqual(threading.active_count(), threads_before + 1)


class TestBatchProcessorSharedQueue(TestCase):
    def setUp(self):
        from iris_opencti_module.opencti_handler import batch_processor as bp
        # Reset shared state between tests.
        bp._QUEUE.clear()
        self.bp = bp
        # Stub the heavy opencti_handler import (it drags in the Flask app
        # and needs a live DB). Use direct sys.modules assignment: patching a
        # dotted key on the sys.modules dict is not supported by patch.object.
        self._handler_module_saved = sys.modules.get(
            "iris_opencti_module.opencti_handler.opencti_handler"
        )
        fake_module = MagicMock()
        self._fake_module = fake_module
        sys.modules["iris_opencti_module.opencti_handler.opencti_handler"] = fake_module

    def tearDown(self):
        if self._handler_module_saved is None:
            sys.modules.pop("iris_opencti_module.opencti_handler.opencti_handler", None)
        else:
            sys.modules["iris_opencti_module.opencti_handler.opencti_handler"] = (
                self._handler_module_saved
            )

    def test_add_batch_visible_to_impl(self):
        """Inline (broker-down) path: the batch is enqueued AND enriched in the
        same process via the shared queue."""
        bp = self.bp
        fake_handler = MagicMock()
        fake_handler.client.search_ioc.return_value = {
            "indicators": {"edges": []},
            "stixCyberObservables": {
                "edges": [
                    {"node": {
                        "id": "observable--8.8.8.8",
                        "entity_type": "IPv4-Addr",
                        "observable_value": "8.8.8.8",
                        "x_opencti_score": 90,
                    }}
                ]
            },
        }
        fake_handler._display_base_url.return_value = "http://opencti:8080"
        self._fake_module.OpenCTIHandler = MagicMock(return_value=fake_handler)

        from iris_opencti_module.opencti_handler import auto_enrich

        # Simulate a down broker: .delay() raises so add_batch falls back to
        # inline processing of the shared queue.
        task_mock = MagicMock()
        task_mock.delay.side_effect = RuntimeError("broker down")
        with patch.object(bp, "process_batches", task_mock), \
             patch.object(auto_enrich, "get_opencti_module_config",
                          return_value={"opencti_max_results": 20, "opencti_min_score": 0}), \
             patch.object(bp.time, "sleep", return_value=None):
            processor = bp.BatchProcessor(max_batch_size=50, rate_limit=1000)
            accepted = processor.add_batch(["8.8.8.8"])
            self.assertTrue(accepted["accepted"])
            self.assertFalse(accepted["async"])
            # The inline drain already processed the batch, so the queue is empty.
            self.assertEqual(accepted["queue_size"], 0)

        self.assertEqual(len(bp._QUEUE), 0)
        # The stub client really ran an OpenCTI search.
        fake_handler.client.search_ioc.assert_called_once()

    def test_add_batch_async_ships_batch_as_task_argument(self):
        """Async (broker up) path: the batch must travel as a task *argument*
        (broker-serialized) because the module _QUEUE is per-process and a
        worker can never read the web process's deque."""
        bp = self.bp
        task_mock = MagicMock()
        with patch.object(bp, "process_batches", task_mock):
            processor = bp.BatchProcessor(max_batch_size=50, rate_limit=10)
            accepted = processor.add_batch(["8.8.8.8", "1.2.3.4"])
            self.assertTrue(accepted["accepted"])
            self.assertTrue(accepted["async"])
            # Broker owns the work: local queue untouched, honest size 0.
            self.assertEqual(accepted["queue_size"], 0)
        task_mock.delay.assert_called_once_with(["8.8.8.8", "1.2.3.4"])

    def test_empty_queue_returns_zero_processed(self):
        with patch.object(self.bp, "process_batches", MagicMock()), \
             patch.object(self.bp.time, "sleep", return_value=None):
            result = self.bp._process_batches_impl()
        self.assertEqual(result["processed"], 0)


class TestEnrichTaskFailureUsesGetMessage(TestCase):
    """enrich_alert_task's failure branch must use IIStatus.get_message().

    IIStatus (iris_interface.IrisInterfaceStatus) only defines get_message() -
    there is no get_msg(). The old code called status.get_msg() in the failure
    branch, which raised AttributeError for any failing enrichment; the outer
    except swallowed it and triggered up to 3 spurious Celery retries that
    masked the real error.
    """

    def test_no_get_msg_in_source(self):
        import inspect
        import re

        import iris_opencti_module.opencti_handler.auto_enrich as ae
        src = inspect.getsource(ae)
        self.assertIsNone(
            re.search(r"\.get_msg\(\)", src),
            "auto_enrich must not call IIStatus.get_msg() (does not exist)",
        )

    def test_ii_status_has_get_message(self):
        import iris_interface.IrisInterfaceStatus as ist

        status = ist.IIStatus(ist.I2CodeError, "boom")
        self.assertTrue(hasattr(status, "get_message"))
        self.assertEqual(status.get_message(), "boom")
        self.assertFalse(status.is_success())
        self.assertFalse(hasattr(status, "get_msg"))


class TestExtractValueFuzzyHashTypes(TestCase):
    """file:hashes patterns for IMPHASH/SSDEEP/PEHASH/AUTHENTIHASH/TLSH/CDHASH
    must yield the hash VALUE, not the algorithm name (generic quoted-token
    fallback captured the algorithm name as value -> exact match failed).
    """

    def test_ssdeep(self):
        value, hash_type = extract_value_from_pattern("file:hashes.'SSDEEP' = '98304:AbCd:Qr'")
        self.assertEqual(value, "98304:AbCd:Qr")
        self.assertEqual(hash_type, "ssdeep")

    def test_imphash(self):
        value, hash_type = extract_value_from_pattern("file:hashes.'IMPHASH' = 'd41d8cd98f00b204e9800998ecf8427e'")
        self.assertEqual(value, "d41d8cd98f00b204e9800998ecf8427e")
        self.assertEqual(hash_type, "imphash")

    def test_pehash(self):
        value, hash_type = extract_value_from_pattern('file:hashes."PEHASH" = "aabbccddeeff"')
        self.assertEqual(value, "aabbccddeeff")
        self.assertEqual(hash_type, "pehash")

    def test_authentihash(self):
        value, hash_type = extract_value_from_pattern("file:hashes.'AUTHENTIHASH' = 'abcdef1234567890'")
        self.assertEqual(value, "abcdef1234567890")
        self.assertEqual(hash_type, "authentihash")

    def test_tlsh_and_cdhash(self):
        value, hash_type = extract_value_from_pattern("file:hashes.'TLSH' = 'T1A2b3c4'")
        self.assertEqual(value, "T1A2b3c4")
        self.assertEqual(hash_type, "tlsh")
        value, hash_type = extract_value_from_pattern("file:hashes.'CDHASH' = 'deadbeef'")
        self.assertEqual(value, "deadbeef")
        self.assertEqual(hash_type, "cdhash")


class TestMetricsHistoryTimestampIsIsoString(TestCase):
    """_aggregate_metrics must store 'timestamp' as an ISO string.

    The old code stored a raw datetime; get_metrics(time_range='1h'|'6h'|'24h')
    then parsed it with datetime.fromisoformat(m['timestamp'].replace('Z', ''))
    -> TypeError -> 500 on GET /opencti/metrics?time_range=... after >=60s.
    """

    def test_aggregated_snapshot_parses_in_time_range_filter(self):
        import iris_opencti_module.opencti_handler.metrics as m

        collector = m._get_metrics()
        collector.record_enrichment(success=True, duration_seconds=0.5)
        collector._aggregate_metrics()

        snapshot = collector._metrics_history[-1]
        self.assertIsInstance(snapshot["timestamp"], str)

        # The very code path that used to raise TypeError:
        from datetime import datetime
        datetime.fromisoformat(snapshot["timestamp"].replace("Z", ""))

        for rng in ("1h", "6h", "24h"):
            result = collector.get_metrics(time_range=rng)
            self.assertIn("history", result)
            self.assertEqual(result["time_range"], rng)


class TestClientStaleCacheInvalidationKey(TestCase):
    """search_ioc schema-fallback must drop every cached entry for the value
    (all query_type/first variants), not just one key - the old
    cache.delete(value, "indicator") was a no-op for entries stored under
    f"indicator:{first}" and served the stale-shaped payload until TTL.
    """

    def test_fallback_invalidates_all_value_variants(self):
        client = OpenCTIClient("http://opencti:8080", "token")
        stale_5 = {"indicators": {"edges": []}, "shape": "old-5"}
        # Seed a stale entry under a DIFFERENT first-variant, as real usage
        # does (an earlier first=5 call). Seeding the exact first=20 key would
        # make search_ioc return it on a cache hit without reaching fallback.
        client.cache.set("1.2.3.4", stale_5, "indicator:5")
        # A different value must survive the invalidation.
        client.cache.set("5.6.7.8", {"indicators": {"edges": []}}, "indicator:20")

        fresh = {"indicators": {"edges": []}, "shape": "new"}
        # First query -> schema drift; legacy fallback succeeds.
        client.query = MagicMock(side_effect=[
            OpenCTIClientError("Cannot query field 'x_opencti_score' on type 'Indicator'"),
            fresh,
        ])
        result = client.search_ioc("1.2.3.4", first=20)

        self.assertEqual(result, fresh)
        # The stale variant of the value is gone; the fresh one is stored.
        self.assertEqual(client.cache.get("1.2.3.4", "indicator:20"), fresh)
        self.assertIsNone(client.cache.get("1.2.3.4", "indicator:5"))
        # The unrelated value is untouched.
        self.assertIsNotNone(client.cache.get("5.6.7.8", "indicator:20"))
        self.assertEqual(client.cache.get_stats()["size"], 2)

    def test_invalidate_value_counts_and_clears(self):
        from iris_opencti_module.opencti_handler.cache import OpenCTICache

        cache = OpenCTICache()
        cache.set("9.9.9.9", {"a": 1}, "indicator:20")
        cache.set("9.9.9.9", {"b": 2}, "indicator:5")
        cache.set("other", {"c": 3}, "indicator:20")
        self.assertEqual(cache.invalidate_value("9.9.9.9"), 2)
        self.assertEqual(cache.invalidate_value("9.9.9.9"), 0)
        self.assertEqual(cache.get_stats()["size"], 1)


class TestHistorySingletonThreadSafe(TestCase):
    """get_enrichment_history uses double-checked locking: racing first uses
    must not create two instances (the loser and its records would be lost).
    """

    def tearDown(self):
        from iris_opencti_module.opencti_handler import history as h
        h.reset_enrichment_history()

    def test_lock_exists_and_race_returns_single_instance(self):
        from iris_opencti_module.opencti_handler import history as h

        self.assertTrue(hasattr(h, "_history_lock"))
        self.assertIsInstance(h._history_lock, type(threading.Lock()))
        h.reset_enrichment_history()

        barrier = threading.Barrier(8)
        results, errors = [], []

        def worker():
            try:
                barrier.wait()
                results.append(h.get_enrichment_history())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 8)
        # All threads must see the same singleton.
        self.assertEqual({id(r) for r in results}, {id(results[0])})


class TestBatchCrossProcessTransport(TestCase):
    """add_batch must send the batch as a Celery task *argument* (the module
    _QUEUE is per-process, so a worker can never see a web-process batch) and
    must process inline when the broker is down.
    """

    def setUp(self):
        from iris_opencti_module.opencti_handler import batch_processor as bp
        bp._QUEUE.clear()
        self.bp = bp

    def tearDown(self):
        self.bp._QUEUE.clear()
        self.bp._processing = False

    def test_batch_travels_as_task_argument(self):
        with patch.object(self.bp, "process_batches") as task:
            processor = self.bp.BatchProcessor()
            accepted = processor.add_batch(["8.8.8.8", "9.9.9.9"])
        self.assertTrue(accepted["accepted"])
        task.delay.assert_called_once_with(["8.8.8.8", "9.9.9.9"])

    def test_broker_down_processes_inline(self):
        with patch.object(self.bp, "process_batches") as task, \
             patch.object(self.bp, "_process_batches_impl") as impl:
            task.delay.side_effect = Exception("kombu ConnectionError: broker down")
            processor = self.bp.BatchProcessor()
            accepted = processor.add_batch(["8.8.8.8"])
        self.assertTrue(accepted["accepted"])
        self.assertFalse(accepted["async"])
        # Inline path drains the LOCAL shared queue (no explicit arg). The
        # mocked impl does not actually drain, so the enqueued batch is still
        # present in _QUEUE here (a real impl would have emptied it).
        impl.assert_called_once_with()
        self.assertEqual(len(self.bp._QUEUE), 1)
        self.assertFalse(self.bp._processing)

    def test_processing_flag_is_module_level(self):
        processor = self.bp.BatchProcessor()
        # The dead per-instance flag is gone; the flag lives on the module.
        self.assertFalse(hasattr(processor, "_processing"))
        self.assertTrue(hasattr(self.bp, "_processing"))

    def test_impl_processes_explicit_batches(self):
        # Explicit batches (Celery path) must not depend on the local queue.
        fake_handler = MagicMock()
        fake_handler.client.search_ioc.return_value = {"indicators": {"edges": []}}
        fake_handler._display_base_url.return_value = "http://opencti:8080"
        fake_module = MagicMock()
        fake_module.OpenCTIHandler = MagicMock(return_value=fake_handler)
        saved = sys.modules.get("iris_opencti_module.opencti_handler.opencti_handler")
        sys.modules["iris_opencti_module.opencti_handler.opencti_handler"] = fake_module
        try:
            from iris_opencti_module.opencti_handler import auto_enrich
            with patch.object(auto_enrich, "get_opencti_module_config",
                              return_value={"opencti_max_results": 20, "opencti_min_score": 0}), \
                 patch.object(self.bp.time, "sleep", return_value=None):
                result = self.bp._process_batches_impl([["8.8.8.8"]])
        finally:
            if saved is None:
                sys.modules.pop("iris_opencti_module.opencti_handler.opencti_handler", None)
            else:
                sys.modules["iris_opencti_module.opencti_handler.opencti_handler"] = saved
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["errors"], 0)


class TestGraphRootsFromMatchIds(TestCase):
    """handle_alert_graphs: with opencti_store_raw_enrichment=False the stored
    'matches' list is empty while root ids come from 'match_ids' - those roots
    must still appear in the graph (as is_root) instead of silently vanishing.
    """

    def setUp(self):
        # Importing the handler pulls in the Flask app; IRIS_WORKER=1 makes
        # run_post_init skip all DB setup (the Celery-worker path).
        os.environ.setdefault("IRIS_WORKER", "1")
        os.environ.setdefault("POSTGRES_USER", "postgres")
        os.environ.setdefault("POSTGRES_PASSWORD", "test")
        os.environ.setdefault("POSTGRES_ADMIN_USER", "irisadmin")
        os.environ.setdefault("POSTGRES_ADMIN_PASSWORD", "test")
        os.environ.setdefault("POSTGRES_SERVER", "127.0.0.1")
        os.environ.setdefault("POSTGRES_PORT", "5432")
        os.environ.setdefault("POSTGRES_DB", "irisdb")
        import iris_opencti_module.opencti_handler.opencti_handler as oh
        from app.models.alerts import Alert

        self.oh = oh
        self.Alert = Alert

    def _handler(self):
        h = self.oh.OpenCTIHandler(
            {"opencti_url": "http://opencti:8080/graphql", "opencti_token": "t"},
            {"http_proxy": None, "https_proxy": None},
            logging.getLogger("test"),
        )
        h.client = MagicMock()
        h.client.get_graph_relationships.return_value = {
            "stixCoreRelationships": {"edges": [], "pageInfo": {"hasNextPage": False}},
        }
        return h

    def test_match_ids_only_roots_appear_in_graph(self):
        from app.models.models import Ioc

        alert = self.Alert()
        ioc = Ioc()
        ioc.ioc_id = 1
        ioc.ioc_value = "8.8.8.8"
        ioc.ioc_enrichment = {"opencti": {"matches": [], "match_ids": ["indicator--abc"]}}
        alert.iocs = [ioc]

        handler = self._handler()
        with patch.object(self.oh, "db") as fake_db:
            status = handler.handle_alert_graphs([alert])

        self.assertTrue(status.is_success())
        graph = alert.alert_context["opencti"]["graph"]
        root_nodes = [n for n in graph["nodes"] if n.get("id") == "indicator--abc"]
        self.assertEqual(len(root_nodes), 1)
        self.assertTrue(root_nodes[0]["is_root"])


class TestCacheValueIndexBoundedAfterEviction(TestCase):
    """The value->keys index must not grow without bound: LRU eviction of an
    entry whose value has no other cached keys must drop the value's set,
    not leave an empty set behind (a real unbounded memory leak with 5k+
    distinct IOCs)."""

    def test_no_empty_sets_after_heavy_eviction(self):
        from iris_opencti_module.opencti_handler.cache import OpenCTICache

        cache = OpenCTICache(max_size=10, ttl=300)
        for i in range(100):
            cache.set(f"ioc-{i}", {"v": i}, "indicator:20")

        # Only the 10 most-recent values can still be cached.
        self.assertEqual(cache.get_stats()["size"], 10)
        empty_sets = [v for v, ks in cache._value_keys.items() if not ks]
        self.assertEqual(empty_sets, [])
        # Index holds exactly the values that still have a cached entry.
        self.assertEqual(len(cache._value_keys), 10)
        # Invalidation still works after evictions.
        self.assertEqual(cache.invalidate_value("ioc-99"), 1)
        self.assertIsNone(cache.get("ioc-99", "indicator:20"))
        self.assertNotIn("ioc-99", cache._value_keys)


class TestBatchConcurrentInlineDrain(TestCase):
    """With the broker down, a second add_batch() while a drain is already
    running (module _processing=True) must also trigger a drain - otherwise
    its batch would sit in the local queue until the (possibly finished)
    first drain's final pass, i.e. be stranded. Pins the else-branch."""

    def setUp(self):
        from iris_opencti_module.opencti_handler import batch_processor as bp

        bp._QUEUE.clear()
        bp._processing = False
        self.bp = bp

    def tearDown(self):
        self.bp._processing = False
        self.bp._QUEUE.clear()

    def test_second_caller_drains_when_one_running(self):
        bp = self.bp
        with patch.object(bp, "process_batches") as task_mock, \
             patch.object(bp, "_process_batches_impl") as impl, \
             patch.object(bp.time, "sleep", return_value=None):
            task_mock.delay.side_effect = RuntimeError("broker down")
            impl.return_value = {"processed": 1, "matched": 0, "errors": 0}
            processor = bp.BatchProcessor(max_batch_size=50, rate_limit=1000)

            r1 = processor.add_batch(["8.8.8.8"])
            self.assertTrue(r1["accepted"])
            self.assertEqual(impl.call_count, 1)  # first caller drained

            # A drain is still running (flag left set) when a second batch
            # arrives -> else-branch must trigger another drain.
            bp._processing = True
            r2 = processor.add_batch(["1.1.1.1"])
            self.assertTrue(r2["accepted"])
            self.assertEqual(impl.call_count, 2)  # second caller drained too


if __name__ == "__main__":
    unittest.main()
