"""Run against a disposable restored PostgreSQL copy and a fake Indexer only."""
import os
if os.environ.get('WAZUH_DISPOSABLE_TEST_DB') != 'yes':
    raise RuntimeError('Set WAZUH_DISPOSABLE_TEST_DB=yes only for an isolated disposable database')

import copy
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import text

from app import app
from app.db import db
from app.business import alerts as alerts_business
from app.business import modules
from app.business.wazuh import MODULE, configuration, prepare_parameter
from app.iris_engine.wazuh import tasks
from app.models.alerts import Alert
from app.models.models import IrisModule
from app.models.wazuh import WazuhPollState, WazuhReceipt

with app.app_context():
    if db.session.execute(text('SELECT current_database()')).scalar() != 'iris_wazuh_test':
        raise RuntimeError('Refusing to run outside iris_wazuh_test')
    if db.session.execute(text('SHOW data_directory')).scalar() != '/var/lib/postgresql/18/docker':
        raise RuntimeError('Refusing to run outside the disposable test database')
    app.config['SECRET_KEY'] = 'isolated-wazuh-test-secret'
    row = IrisModule.query.filter_by(module_name=MODULE).one()
    assert not row.is_active
    config = copy.deepcopy(row.module_config)
    values = {'url': 'https://indexer.invalid', 'username': 'test-reader',
              'password': prepare_parameter('password', 'test-password'),
              'interval': '1', 'verify_tls': True}
    for parameter in config:
        if parameter['param_name'] in values:
            parameter['value'] = values[parameter['param_name']]
    row.module_config = config
    db.session.commit()
    visible = modules.module_get_detail(row.id)
    secret = next(p for p in visible['module_config'] if p['param_name'] == 'password')
    assert secret['value'] == '' and secret['has_value']
    with patch.object(modules, 'iris_update_hooks', return_value=(True, [])), \
         patch.object(modules, 'track_activity'):
        modules.modules_enable(row.id)
    config = configuration(row)
    with tasks.source_lock(config['source_key']) as first:
        with tasks.source_lock(config['source_key']) as second:
            assert first and not second
    state = db.session.get(WazuhPollState, config['source_key'])
    assert state.started_at == state.watermark
    start = state.started_at
    timestamp = lambda t: t.replace(tzinfo=timezone.utc).isoformat()
    def hit(identifier, when, level):
        return {'_index': 'wazuh-alerts-4.x-test', '_id': identifier,
                '_source': {'timestamp': timestamp(when), 'rule': {'level': level, 'description': identifier},
                            'agent': {'id': '001'}, 'data': {'srcip': '192.0.2.1'}}}
    events = [hit('old', start - timedelta(seconds=1), 15),
              hit('high1', start + timedelta(seconds=1), 12),
              hit('high2', start + timedelta(seconds=1), 14),
              hit('low', start + timedelta(seconds=1), 11)]
    class FakeClient:
        def __init__(self, *args): pass
        def hits(self, begin, end, level):
            for item in events:
                when = item['_source']['timestamp']
                if begin <= when < end and item['_source']['rule']['level'] >= level:
                    yield item
        def close(self): pass
    class FakeDateTime(datetime):
        current = start + timedelta(seconds=31)
        @classmethod
        def now(cls, tz=None):
            return cls.current.replace(tzinfo=timezone.utc)
    original = Alert.query.count()
    with ExitStack() as stack:
        stack.enter_context(patch.object(tasks, 'Client', FakeClient))
        stack.enter_context(patch.object(tasks, 'datetime', FakeDateTime))
        for name in ('add_obj_history_entry', 'cache_similar_alert', 'track_activity',
                     '_enqueue_rule_evaluation', 'managed_assets_observe_alert'):
            stack.enter_context(patch.object(alerts_business, name))
        stack.enter_context(patch.object(alerts_business, 'call_modules_hook', side_effect=lambda _name, alert: alert))
        stack.enter_context(patch.object(alerts_business.socket_io, 'emit'))
        tasks.poll.run(row.id)
        db.session.expire_all()
        assert Alert.query.count() == original + 2
        imported = Alert.query.filter_by(alert_source='Wazuh').all()
        assert {item.alert_source_ref.rsplit(':', 1)[-1] for item in imported} == {'high1', 'high2'}
        assert all(item.alert_source_content['agent']['id'] == '001' for item in imported)
        imported[0].alert_title = 'analyst edit'
        db.session.commit()
        FakeDateTime.current += timedelta(seconds=31)
        tasks.poll.run(row.id)
        db.session.expire_all()
        assert Alert.query.count() == original + 2
        assert Alert.query.filter_by(alert_title='analyst edit').count() == 1
        assert WazuhReceipt.query.filter_by(source_key=config['source_key']).count() == 2
        prior_watermark = db.session.get(WazuhPollState, config['source_key']).watermark
        events.extend([hit('high3', start + timedelta(seconds=2), 12),
                       hit('high4', start + timedelta(seconds=2), 12)])
        class FailingClient(FakeClient):
            def hits(self, begin, end, level):
                yield events[-2]
                raise ConnectionError('synthetic second-page failure')
        FakeDateTime.current += timedelta(seconds=31)
        with patch.object(tasks, 'Client', FailingClient):
            tasks.poll.run(row.id)
        db.session.expire_all()
        assert db.session.get(WazuhPollState, config['source_key']).watermark == prior_watermark
        assert Alert.query.count() == original + 3
        FakeDateTime.current += timedelta(seconds=31)
        tasks.poll.run(row.id)
        db.session.expire_all()
        assert Alert.query.count() == original + 4
        assert WazuhReceipt.query.filter_by(source_key=config['source_key']).count() == 4
    print('Isolated IRIS enable, PostgreSQL worker poll, threshold, history boundary and deduplication passed')
