"""Second-process deduplication check against a disposable test database."""
import os
if os.environ.get('WAZUH_DISPOSABLE_TEST_DB') != 'yes':
    raise RuntimeError('Set WAZUH_DISPOSABLE_TEST_DB=yes only for an isolated disposable database')

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import text
from app import app
from app.db import db
from app.business.wazuh import MODULE, configuration
from app.iris_engine.wazuh import tasks
from app.models.alerts import Alert
from app.models.models import IrisModule
from app.models.wazuh import WazuhPollState, WazuhReceipt

with app.app_context():
    if (db.session.execute(text('SELECT current_database()')).scalar() != 'iris_wazuh_test'
            or db.session.execute(text('SHOW data_directory')).scalar() != '/var/lib/postgresql/18/docker'):
        raise RuntimeError('Refusing to run outside the disposable test database')
    app.config['SECRET_KEY'] = 'isolated-wazuh-test-secret'
    row = IrisModule.query.filter_by(module_name=MODULE).one()
    assert row.is_active
    config = configuration(row)
    state = db.session.get(WazuhPollState, config['source_key'])
    before = Alert.query.count()
    receipts_before = WazuhReceipt.query.filter_by(source_key=config['source_key']).count()
    assert receipts_before == 4
    assert Alert.query.filter_by(alert_title='analyst edit').count() == 1
    event_time = state.started_at + timedelta(seconds=1)
    hit = {'_index': 'wazuh-alerts-4.x-test', '_id': 'high1',
           '_source': {'timestamp': event_time.replace(tzinfo=timezone.utc).isoformat(),
                       'rule': {'level': 12, 'description': 'high1'}}}
    class FakeClient:
        def __init__(self, *args): pass
        def hits(self, _begin, _end, _level):
            yield hit
        def close(self): pass
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (state.last_poll + timedelta(seconds=31)).replace(tzinfo=timezone.utc)
    with patch.object(tasks, 'Client', FakeClient), patch.object(tasks, 'datetime', FakeDateTime):
        tasks.poll.run(row.id)
    db.session.expire_all()
    assert Alert.query.count() == before
    assert WazuhReceipt.query.filter_by(source_key=config['source_key']).count() == receipts_before
    assert Alert.query.filter_by(alert_title='analyst edit').count() == 1
print('Fresh-process PostgreSQL deduplication passed')
