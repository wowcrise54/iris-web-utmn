"""Exercise durable receipts with real SQL transactions and stubbed IRIS hooks."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import copy
import sys
import types
from unittest.mock import patch

from sqlalchemy import Column, DateTime, Integer, String, select
import pytest
import requests

from test_maxpatrol_storage import harness, load


def test_activation_and_repeat_after_restart_preserve_analyst_edits(caplog):
    with harness() as h:
        h.Alert.alert_description = Column(String)
        h.Alert.alert_source_event_time = Column(DateTime)
        h.Alert.alert_severity_id = Column(Integer)
        h.Alert.alert_status_id = Column(Integer)
        models = load('app.models.wazuh', 'app/models/wazuh.py')
        business = load('app.business.wazuh', 'app/business/wazuh.py')
        try:
            encrypted = business.prepare_parameter('password', 'secret')
            assert encrypted == 'encrypted:secret'
            assert business.prepare_parameter('password', '', encrypted) == encrypted
            visible = business.public_config([{'param_name': 'password', 'value': encrypted}])
            assert visible[0]['value'] == '' and visible[0]['has_value']
            assert business.prepare_parameter('verify_tls', True) is True
            assert business.prepare_parameter('verify_tls', 'false') is False
            with pytest.raises(ValueError):
                business.prepare_parameter('verify_tls', 'not-a-boolean')
            # The harness creates its tables before Wazuh is loaded.
            h.db.Model.metadata.drop_all(h.db.engine)
            h.db.Model.metadata.create_all(h.db.engine)
            h.db.session.add(h.Module(id=2, module_name=business.MODULE, is_active=True, module_config=[
                {'param_name': name, 'value': value} for name, value in {
                    'url': 'https://indexer.local', 'username': 'reader', 'password': 'encrypted:secret',
                    'index': 'wazuh-alerts-4.x-*', 'customer_id': '1', 'severity_id': '1',
                    'status_id': '5', 'interval': '30', 'timeout': '30', 'min_level': '12',
                    'verify_tls': True}.items()]))
            h.db.session.commit()
            row = h.db.session.get(h.Module, 2)
            business.initialize(row)
            config = business.configuration(row)
            upper_path = copy.deepcopy(row.module_config)
            lower_path = copy.deepcopy(row.module_config)
            next(p for p in upper_path if p['param_name'] == 'url')['value'] = 'https://INDEXER.local/Proxy'
            next(p for p in lower_path if p['param_name'] == 'url')['value'] = 'https://indexer.local/proxy'
            assert business.configuration(types.SimpleNamespace(module_config=upper_path))['source_key'] != \
                business.configuration(types.SimpleNamespace(module_config=lower_path))['source_key']
            next(p for p in upper_path if p['param_name'] == 'url')['value'] = 'https://INDEXER.local/proxy/'
            assert business.configuration(types.SimpleNamespace(module_config=upper_path))['source_key'] == \
                business.configuration(types.SimpleNamespace(module_config=lower_path))['source_key']
            state = h.db.session.get(models.WazuhPollState, config['source_key'])
            assert state.started_at == state.watermark
            initial = state.started_at
            business.initialize(row)
            assert state.started_at == initial
            def create(alert, **kwargs):
                h.db.session.add(alert)
                h.db.session.commit()
            h.alerts.alerts_create = create
            hit = {'_index': 'wazuh-alerts-4.x-2026.11.06', '_id': 'x',
                   '_source': {'timestamp': '2026-11-06T10:00:00Z', 'rule': {'level': 12}}}
            store = business.IrisStore(2, config, state)
            assert not store.seen(hit)
            def fail_before_commit(alert, **kwargs):
                h.db.session.add(alert)
                raise RuntimeError('before commit')
            h.alerts.alerts_create = fail_before_commit
            with pytest.raises(RuntimeError):
                store.create(hit)
            h.db.session.rollback()
            assert not store.seen(hit)
            h.alerts.alerts_create = create
            store.create(hit)
            alert = h.db.session.scalars(select(h.Alert)).one()
            alert.alert_title = 'Analyst edited'
            h.db.session.commit()
            h.db.session.expunge_all()
            state = h.db.session.get(models.WazuhPollState, config['source_key'])
            store = business.IrisStore(2, config, state)
            assert store.seen(hit)
            assert h.db.session.scalars(select(h.Alert)).one().alert_title == 'Analyst edited'
            assert len(h.db.session.scalars(select(models.WazuhReceipt)).all()) == 1
            second = {**hit, '_id': 'y'}  # Same timestamp, distinct document.
            def fail_after_commit(alert, **kwargs):
                create(alert, **kwargs)
                raise RuntimeError('after commit')
            h.alerts.alerts_create = fail_after_commit
            with pytest.raises(RuntimeError):
                store.create(second)
            h.db.session.rollback()
            h.db.session.expunge_all()
            state = h.db.session.get(models.WazuhPollState, config['source_key'])
            store = business.IrisStore(2, config, state)
            assert store.seen(second)
            assert len(h.db.session.scalars(select(h.Alert)).all()) == 2
            old_watermark = state.watermark
            row = h.db.session.get(h.Module, 2)
            row.is_active = False
            h.db.session.commit()
            with pytest.raises(ValueError, match='disabled or settings changed'):
                store.advance(old_watermark + timedelta(hours=1))
            h.db.session.rollback()
            assert state.watermark == old_watermark
            row.is_active = True
            h.db.session.commit()

            @contextmanager
            def source_lock(_key):
                yield True
            lock_module = types.ModuleType('app.iris_engine.maxpatrol.tasks')
            lock_module.source_lock = source_lock
            with patch.dict(sys.modules, {'app.iris_engine.maxpatrol.tasks': lock_module}):
                tasks = load('wazuh_test_tasks', 'app/iris_engine/wazuh/tasks.py')
                calls = []
                third = {**hit, '_id': 'z'}
                class Client:
                    def __init__(self, *args): pass
                    def hits(self, start, end, level):
                        calls.append((start, end, level))
                        yield hit
                        yield second
                        yield third
                    def close(self): pass
                tasks.Client = Client
                h.alerts.alerts_create = create
                state.last_poll = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=31)
                old_watermark = state.watermark
                h.db.session.commit()
                tasks.poll(2)
                h.db.session.expire_all()
                state = h.db.session.get(models.WazuhPollState, config['source_key'])
                assert state.watermark >= old_watermark
                assert calls[0][0] == tasks.timestamp(initial)
                assert calls[0][2] == 12
                assert len(h.db.session.scalars(select(h.Alert)).all()) == 3
                assert len(h.db.session.scalars(select(models.WazuhReceipt)).all()) == 3
                fourth = {**hit, '_id': 'four'}
                fifth = {**hit, '_id': 'five'}
                class FailingClient(Client):
                    def hits(self, start, end, level):
                        yield fourth
                        raise ConnectionError('simulated failure exposing secret')
                tasks.Client = FailingClient
                state.last_poll = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=31)
                previous_watermark = state.watermark
                h.db.session.commit()
                tasks.poll(2)
                assert 'secret' not in caplog.text
                assert 'processing failed; retry scheduled' in caplog.text
                h.db.session.expire_all()
                state = h.db.session.get(models.WazuhPollState, config['source_key'])
                assert state.watermark == previous_watermark
                assert len(h.db.session.scalars(select(h.Alert)).all()) == 4
                class RetryClient(Client):
                    def hits(self, start, end, level):
                        yield fourth
                        yield fifth
                tasks.Client = RetryClient
                state.last_poll = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=31)
                h.db.session.commit()
                tasks.poll(2)
                h.db.session.expire_all()
                state = h.db.session.get(models.WazuhPollState, config['source_key'])
                assert state.watermark >= previous_watermark
                assert len(h.db.session.scalars(select(h.Alert)).all()) == 5
                assert len(h.db.session.scalars(select(models.WazuhReceipt)).all()) == 5
                response = requests.Response()
                response.status_code = 401
                failures = [(requests.exceptions.SSLError('secret'), 'TLS verification failed'),
                            (requests.exceptions.ConnectionError('secret'), 'Indexer connection failed'),
                            (requests.exceptions.Timeout('secret'), 'Indexer request timed out'),
                            (requests.exceptions.HTTPError('secret', response=response), 'Indexer returned HTTP 401')]
                for error, expected_reason in failures:
                    class ErrorClient(Client):
                        def hits(self, start, end, level):
                            raise error
                            yield
                    tasks.Client = ErrorClient
                    state.last_poll = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=31)
                    previous_watermark = state.watermark
                    h.db.session.commit()
                    caplog.clear()
                    tasks.poll(2)
                    h.db.session.expire_all()
                    state = h.db.session.get(models.WazuhPollState, config['source_key'])
                    assert state.watermark == previous_watermark
                    assert expected_reason in caplog.text and 'secret' not in caplog.text
                sys.modules.pop('wazuh_test_tasks', None)
        finally:
            sys.modules.pop('app.business.wazuh', None)
            sys.modules.pop('app.models.wazuh', None)
