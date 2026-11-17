import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from iris_wazuh_module.collector import search_body, make_alert


def test_search_filters_window_and_level():
    body = search_body('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', 12)
    assert {'range': {'rule.level': {'gte': 12}}} in body['query']['bool']['filter']
    assert body['size'] <= 500
    assert body['sort'] == [{'timestamp': 'asc'}, '_doc']


def test_preserves_source_and_identifier():
    hit = {'_index': 'wazuh-alerts-4.x-2026.01.01', '_id': 'abc', '_source': {'timestamp': '2026-01-01T00:00:00Z', 'rule': {'level': 12, 'description': 'test'}}}
    result = make_alert(hit, 1, 1, 5)
    assert result['alert_source_ref'] == 'wazuh-alerts-4.x-2026.01.01:abc'
    assert result['alert_source_content'] == hit['_source']
    assert result['alert_source_event_time'] == datetime(2026, 1, 1)


def test_client_iterates_scroll_and_clears_it():
    from iris_wazuh_module.collector import Client
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload
    class Session:
        def __init__(self): self.calls = []
        def post(self, url, **kw):
            self.calls.append((url, kw))
            if len(self.calls) == 1:
                return Response({'_scroll_id': 'scroll-1', 'timed_out': False, '_shards': {'failed': 0}, 'hits': {'hits': [{'_id': '1'}]}})
            return Response({'_scroll_id': 'scroll-2', 'timed_out': False, '_shards': {'failed': 0}, 'hits': {'hits': []}})
        def delete(self, url, **kw): self.calls.append((url, kw))
    session = Session()
    client = Client('https://indexer.example', 'user', 'password', 'wazuh-alerts-4.x-*', session=session)
    assert list(client.hits('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', 12)) == [{'_id': '1'}]
    assert session.calls[-1][1]['json'] == {'scroll_id': ['scroll-2']}


def test_collection_retries_failed_window_without_duplicates():
    from iris_wazuh_module.collector import collect_window
    class Store:
        def __init__(self): self.saved = set(); self.watermark = 0
        def seen(self, hit): return hit in self.saved
        def create(self, hit):
            if hit == 'b' and len(self.saved) == 1: raise RuntimeError('failure')
            self.saved.add(hit)
        def advance(self, value): self.watermark = value
    store = Store()
    import pytest
    with pytest.raises(RuntimeError): collect_window(iter(['a', 'b']), store, 10)
    assert store.watermark == 0 and store.saved == {'a'}
    store.saved.add('b')
    collect_window(iter(['a', 'b', 'c']), store, 10)
    assert store.watermark == 10 and store.saved == {'a', 'b', 'c'}


def test_scroll_rejects_partial_results_and_cleans_up():
    import pytest
    from iris_wazuh_module.collector import Client
    class Response:
        def __init__(self, body): self.body = body
        def raise_for_status(self): pass
        def json(self): return self.body
    class Session:
        def __init__(self): self.calls = 0; self.deleted = []
        def post(self, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return Response({'_scroll_id': 'one', 'timed_out': False, '_shards': {'failed': 0}, 'hits': {'hits': [{'_id': 'a'}]}})
            return Response({'_scroll_id': 'two', 'timed_out': True, '_shards': {'failed': 0}, 'hits': {'hits': []}})
        def delete(self, url, **kwargs): self.deleted.append(kwargs['json'])
    session = Session()
    client = Client('https://indexer.example', 'user', 'password', 'wazuh-alerts-4.x-*', session=session)
    with pytest.raises(ValueError, match='incomplete'):
        list(client.hits('start', 'end', 12))
    assert session.deleted == [{'scroll_id': ['one']}]


def test_scroll_failure_does_not_advance_watermark():
    import pytest
    from iris_wazuh_module.collector import collect_window
    class Store:
        watermark = 0
        def seen(self, hit): return False
        def create(self, hit): pass
        def advance(self, value): self.watermark = value
    def hits():
        yield 'first'
        raise ConnectionError('Indexer disconnected')
    store = Store()
    with pytest.raises(ConnectionError): collect_window(hits(), store, 1)
    assert store.watermark == 0


def test_search_http_failures_propagate_without_advancing():
    import pytest
    import requests
    from iris_wazuh_module.collector import Client, collect_window
    class Store:
        watermark = 0
        def seen(self, hit): return False
        def create(self, hit): raise AssertionError('unexpected hit')
        def advance(self, value): self.watermark = value
    class Session:
        def __init__(self, error): self.error = error
        def post(self, url, **kwargs):
            assert kwargs['auth'] == ('reader', 'secret')
            raise self.error
    for error in (requests.ConnectionError('offline'), requests.Timeout('timeout'),
                  requests.exceptions.SSLError('TLS'), requests.HTTPError('401')):
        store = Store()
        client = Client('https://indexer.example', 'reader', 'secret', 'wazuh-alerts-4.x-*', session=Session(error))
        with pytest.raises(type(error)):
            collect_window(client.hits('start', 'end', 12), store, 1)
        assert store.watermark == 0


def test_bad_response_does_not_advance_watermark():
    import pytest
    from iris_wazuh_module.collector import Client, collect_window
    class Store:
        watermark = 0
        def seen(self, hit): return False
        def create(self, hit): pass
        def advance(self, value): self.watermark = value
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'unexpected': 'shape'}
    class Session:
        def post(self, *args, **kwargs): return Response()
    store = Store()
    client = Client('https://indexer.example', 'reader', 'secret', 'wazuh-alerts-4.x-*', session=Session())
    with pytest.raises(ValueError): collect_window(client.hits('start', 'end', 12), store, 1)
    assert store.watermark == 0


def test_postgres_checks_refuse_to_run_without_disposable_database_opt_in():
    import os
    import subprocess
    env = os.environ.copy()
    env.pop('WAZUH_DISPOSABLE_TEST_DB', None)
    root = Path(__file__).resolve().parent
    for name in ('wazuh_postgres_check.py', 'wazuh_copy_upgrade_check.py', 'wazuh_end_to_end_check.py',
                 'wazuh_restart_check.py'):
        result = subprocess.run([sys.executable, str(root / name)], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert 'WAZUH_DISPOSABLE_TEST_DB' in result.stderr
