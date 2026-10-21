"""Real SQL transactions with SQLite; app/broker boundaries are inert doubles."""
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

from sqlalchemy import Boolean, Column, Integer, JSON, String, Uuid, create_engine, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects import postgresql  # noqa: F401  register before temporary sys.modules isolation

SOURCE = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0, str(SOURCE))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, SOURCE / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def harness():
    base = declarative_base()

    class Module(base):
        __tablename__ = 'iris_modules'
        id = Column(Integer, primary_key=True)
        module_name = Column(String)
        module_config = Column(JSON)
        is_active = Column(Boolean)

    class Alert(base):
        __tablename__ = 'alerts'
        id = Column(Integer, primary_key=True)
        alert_uuid = Column(Uuid, unique=True)
        alert_title = Column(String)
        alert_customer_id = Column(Integer)
        alert_source = Column(String)
        alert_source_ref = Column(String)
        alert_source_content = Column(JSON)

    engine = create_engine('sqlite://')
    session = sessionmaker(bind=engine)()
    db = types.SimpleNamespace(Model=base, session=session, engine=engine)
    module_names = ('app', 'app.db', 'app.models', 'app.models.models', 'app.models.errors',
                    'app.models.alerts', 'app.business', 'app.business.alerts',
                    'app.iris_engine', 'app.iris_engine.mail', 'app.iris_engine.mail.secrets')
    doubles = {name: types.ModuleType(name) for name in module_names}
    doubles['app.db'].db = db
    doubles['app.models.models'].IrisModule = Module
    doubles['app.models.errors'].BusinessProcessingError = ValueError
    doubles['app.models.alerts'].Alert = Alert
    doubles['app.business.alerts'].alerts_create = Mock()
    doubles['app.iris_engine.mail.secrets'].encrypt_secret = lambda value: 'encrypted:' + value
    doubles['app.iris_engine.mail.secrets'].decrypt_secret = lambda value: value.removeprefix('encrypted:') if value else None
    celery = types.SimpleNamespace(task=lambda **_kwargs: lambda f: f,
                                   conf=types.SimpleNamespace(beat_schedule={}))
    doubles['app'].celery = celery
    names = ['app.models.maxpatrol', 'app.business.maxpatrol', 'maxpatrol_test_tasks']
    original = {name: sys.modules.get(name) for name in names}
    with patch.dict(sys.modules, doubles):
        try:
            models = load('app.models.maxpatrol', 'app/models/maxpatrol.py')
            business = load('app.business.maxpatrol', 'app/business/maxpatrol.py')
            tasks = load('maxpatrol_test_tasks', 'app/iris_engine/maxpatrol/tasks.py')
            base.metadata.create_all(engine)
            row = Module(id=1, module_name=business.MODULE, is_active=True, module_config=[
                {'param_name': 'siem_url', 'value': 'https://siem.local'},
                {'param_name': 'api_token', 'value': 'encrypted:secret'}])
            session.add(row)
            session.commit()
            config = business.configuration(row)
            yield types.SimpleNamespace(db=db, business=business, models=models, tasks=tasks,
                store=business.IrisStore(1, config), config=config, Module=Module, Alert=Alert,
                alerts=doubles['app.business.alerts'])
        finally:
            session.close()
            engine.dispose()
            for name, value in original.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value


class StorageTests(unittest.TestCase):
    def test_create_removes_null_fields_before_database_commit(self):
        with harness() as h:
            def create(alert, **kwargs):
                h.db.session.add(alert)
                h.db.session.commit()

            h.alerts.alerts_create = create
            raw_body = '{"Original": null}'
            source = {'incident': {'id': 'one', 'assigned': None},
                'events': [{'uuid': '00000006-050d-0642-f000-0000255d3663',
                    'subject.account.domain': None, 'body': raw_body,
                    'historical': False, 'count': 0, 'text': '',
                    'nested': {'empty': None, 'present': 'value'},
                    'items': [{'remove': None, 'keep': False}, None]}],
                'incident_refresh_error': None}
            h.store.create('one', {'alert_title': 'One', 'alert_source_content': source})
            h.db.session.expire_all()
            saved = h.db.session.query(h.Alert).one().alert_source_content
            self.assertNotIn('assigned', saved['incident'])
            self.assertNotIn('incident_refresh_error', saved)
            row = saved['events'][0]
            self.assertNotIn('subject.account.domain', row)
            self.assertEqual(row['nested'], {'present': 'value'})
            self.assertEqual(row['body'], raw_body)
            self.assertIs(row['historical'], False)
            self.assertEqual(row['count'], 0)
            self.assertEqual(row['text'], '')
            self.assertEqual(row['items'], [{'keep': False}, None])
            self.assertIn('subject.account.domain', source['events'][0])

    def test_refresh_removes_old_and_incoming_null_fields_in_flat_and_tree_data(self):
        with harness() as h:
            from uuid import uuid4
            uid = '00000006-050d-0642-f000-0000255d3663'
            alert_uuid = uuid4()
            h.db.session.add(h.models.MaxPatrolReceipt(source_key=h.config.source_key,
                incident_id='one', alert_uuid=alert_uuid,
                imported_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            h.db.session.add(h.Alert(alert_uuid=alert_uuid, alert_title='Keep analyst title',
                alert_customer_id=1, alert_source='MaxPatrol SIEM', alert_source_ref='one',
                alert_source_content={'custom': {'old_null': None, 'keep': 0},
                    'events': [{'uuid': uid, 'old_null': None, 'body': 'original'}],
                    'event_tree': [{'uuid': uid}], 'event_links': {uid: []}}))
            h.db.session.commit()
            h.store.refresh_events('one', {'events': [{'uuid': uid, 'new_null': None, 'flag': False}],
                'event_tree': [{'uuid': uid}], 'event_collection': {'version': 2, 'complete': False}})
            h.db.session.expire_all()
            saved = h.db.session.query(h.Alert).one()
            self.assertEqual(saved.alert_title, 'Keep analyst title')
            self.assertEqual(saved.alert_source_content['custom'], {'keep': 0})
            row = saved.alert_source_content['events'][0]
            self.assertNotIn('old_null', row)
            self.assertNotIn('new_null', row)
            self.assertEqual(row['body'], 'original')
            self.assertIs(row['flag'], False)
            self.assertEqual(saved.alert_source_content['event_tree'][0]['event'], row)

    def test_refresh_updates_only_source_materials_and_preserves_previous_events(self):
        with harness() as h:
            from iris_maxpatrol_module.collector import timestamp

            def create(alert, **kwargs):
                h.db.session.add(alert)
                h.db.session.commit()
            h.alerts.alerts_create = create
            uid = '00000006-050d-0642-f000-0000255d3663'
            h.store.create('one', {'alert_title': 'Analyst title', 'alert_customer_id': 1,
                'alert_source': 'MaxPatrol SIEM', 'alert_source_ref': 'one',
                'alert_source_content': {'custom': 'preserved', 'incident': {'id': 'one', 'name': 'Saved card'},
                                         'events': [{'uuid': uid, 'body': 'raw'}]}})
            saved = h.store.stored_incident('one')
            self.assertEqual(saved['name'], 'Saved card')
            saved['name'] = 'Changed outside storage'
            self.assertEqual(h.store.stored_incident('one')['name'], 'Saved card')
            self.assertTrue(h.store.needs_event_refresh('one'))
            self.assertEqual(h.store.refresh_candidates(), ['one'])
            incoming = {'events': [{'uuid': uid, 'text': 'normalized'}], 'event_tree': [{'uuid': uid}],
                        'event_collection': {'version': 2, 'complete': True,
                            'collected_at': timestamp(datetime.now(timezone.utc))}}
            self.assertTrue(h.store.refresh_events('one', incoming))
            row = h.db.session.query(h.Alert).one()
            self.assertEqual(row.alert_title, 'Analyst title')
            self.assertEqual(row.alert_source_content['custom'], 'preserved')
            self.assertEqual(row.alert_source_content['events'][0]['body'], 'raw')
            self.assertEqual(row.alert_source_content['events'][0]['text'], 'normalized')
            self.assertFalse(h.store.needs_event_refresh('one'))
            self.assertEqual(h.store.refresh_candidates(), [])
            child = '00000006-050d-0642-f000-0000255d3664'
            grandchild = '00000006-050d-0642-f000-0000255d3665'
            h.store.refresh_events('one', {'events': [{'uuid': child}, {'uuid': grandchild}],
                'event_links': {uid: [child], child: [grandchild], grandchild: []},
                'event_tree': [{'uuid': uid}],
                'event_collection': {'version': 2, 'complete': True,
                    'collected_at': timestamp(datetime.now(timezone.utc))}})
            h.store.refresh_events('one', {'events': [{'uuid': uid}, {'uuid': child}],
                'event_links': {uid: [child], child: []}, 'event_tree': [{'uuid': uid}],
                'event_collection': {'version': 2, 'complete': False}})
            row = h.db.session.query(h.Alert).one()
            self.assertEqual(row.alert_source_content['event_links'][child], [grandchild])
            tree = row.alert_source_content['event_tree'][0]
            self.assertEqual(tree['subevents'][0]['subevents'][0]['uuid'], grandchild)
            h.db.session.delete(row)
            h.db.session.commit()
            self.assertFalse(h.store.needs_event_refresh('one'))

    def test_receipt_atomic_with_alert_and_survives_restart_and_deletion(self):
        with harness() as h:
            def create(alert, **kwargs):
                h.db.session.add(alert)
                h.db.session.commit()
            h.alerts.alerts_create = create
            h.store.create('one', {'alert_title': 'One'})
            h.db.session.close()
            self.assertTrue(h.business.IrisStore(1, h.config).seen('one'))
            h.db.session.query(h.Alert).delete()
            h.db.session.commit()
            self.assertTrue(h.store.seen('one'))
            with self.assertRaises(IntegrityError):
                h.store.create('one', {'alert_title': 'Duplicate'})
            h.store.rollback()
            self.assertEqual(h.db.session.scalar(select(func.count()).select_from(h.Alert)), 0)

    def test_failure_before_commit_rolls_back_receipt_and_alert(self):
        with harness() as h:
            def fail(alert, **kwargs):
                h.db.session.add(alert)
                h.db.session.flush()
                raise RuntimeError('before commit')
            h.alerts.alerts_create = fail
            with self.assertRaises(RuntimeError):
                h.store.create('one', {'alert_title': 'One'})
            h.store.rollback()
            self.assertFalse(h.store.seen('one'))
            self.assertEqual(h.db.session.scalar(select(func.count()).select_from(h.Alert)), 0)

    def test_failure_after_commit_keeps_receipt_and_alert(self):
        with harness() as h:
            def fail(alert, **kwargs):
                h.db.session.add(alert)
                h.db.session.commit()
                raise RuntimeError('hook after commit')
            h.alerts.alerts_create = fail
            with self.assertRaises(RuntimeError):
                h.store.create('one', {'alert_title': 'One'})
            h.store.rollback()
            h.db.session.close()
            self.assertTrue(h.store.seen('one'))
            self.assertEqual(h.db.session.scalar(select(func.count()).select_from(h.Alert)), 1)

    def test_source_identity_scoped_and_token_rotation_keeps_receipts(self):
        with harness() as h:
            config = h.business.Config.from_values
            base = {'siem_url': 'https://siem.local', 'api_token': 'changed'}
            self.assertEqual(h.config.source_key, config(base).source_key)
            self.assertEqual(h.config.source_key, config({**base, 'siem_url': 'https://SIEM.local:443/'}).source_key)
            self.assertNotEqual(h.config.source_key, config({**base, 'customer_id': 2}).source_key)
            self.assertNotEqual(h.config.source_key, config({**base, 'siem_url': 'https://other.local'}).source_key)

    def test_disable_and_configuration_change_prevent_inflight_create(self):
        with harness() as h:
            row = h.db.session.get(h.Module, 1)
            row.is_active = False
            h.db.session.commit()
            self.assertFalse(h.store.active())
            with self.assertRaises(ValueError):
                h.store.create('one', {'alert_title': 'One'})
            row.is_active = True
            row.module_config = [{'param_name': 'siem_url', 'value': 'https://other.local'},
                                 {'param_name': 'api_token', 'value': 'encrypted:secret'}]
            h.db.session.commit()
            self.assertFalse(h.store.active())

    def test_secret_preserved_on_blank_edit_and_masked_on_export(self):
        with harness() as h:
            business = h.business
            encrypted = business.prepare_parameter('api_token', 'secret')
            self.assertNotEqual(encrypted, 'secret')
            self.assertEqual(business.prepare_parameter('api_token', '', encrypted), encrypted)
            values = [{'param_name': 'api_token', 'value': encrypted}]
            self.assertEqual(business.public_config(values)[0]['value'], '')
            self.assertEqual(values[0]['value'], encrypted)

    def test_poll_interval_and_disabled_module_never_contact_siem(self):
        with harness() as h, patch('maxpatrol_test_tasks.source_lock') as lock, \
                patch('maxpatrol_test_tasks.Client') as client:
            lock.return_value.__enter__.return_value = True
            h.db.session.add(h.models.MaxPatrolPollState(source_key=h.config.source_key,
                last_poll=datetime.now(timezone.utc).replace(tzinfo=None)))
            h.db.session.commit()
            h.tasks.poll(1)
            client.assert_not_called()
            row = h.db.session.get(h.Module, 1)
            row.is_active = False
            h.db.session.commit()
            h.tasks.poll(1)
            client.assert_not_called()

    def test_advisory_lock_released_after_poll_exception_and_invalidated_on_unlock_error(self):
        with harness() as h:
            connection = Mock()
            h.db.engine = MagicMock()
            h.db.engine.connect.return_value.__enter__.return_value = connection
            connection.execute.return_value.scalar.return_value = True
            with self.assertRaises(RuntimeError):
                with h.tasks.source_lock(h.config.source_key) as acquired:
                    self.assertTrue(acquired)
                    raise RuntimeError('poll failed')
            self.assertIn('pg_advisory_unlock', str(connection.execute.call_args.args[0]))
            connection.execute.side_effect = [Mock(scalar=lambda: True), RuntimeError('connection lost')]
            with h.tasks.source_lock(h.config.source_key):
                pass
            connection.invalidate.assert_called_once()

    def test_due_poll_records_attempt_and_closes_client_on_request_failure(self):
        with harness() as h, patch('maxpatrol_test_tasks.source_lock') as lock, \
                patch('maxpatrol_test_tasks.Client') as client, \
                patch('maxpatrol_test_tasks.collect', side_effect=RuntimeError('SIEM unavailable')) as collect:
            lock.return_value.__enter__.return_value = True
            h.tasks.poll(1)
            collect.assert_called_once()
            client.return_value.close.assert_called_once()
            self.assertIsNotNone(h.db.session.get(h.models.MaxPatrolPollState, h.config.source_key))
            # Failed polls respect the interval, avoiding a tight retry loop.
            h.tasks.poll(1)
            self.assertEqual(collect.call_count, 1)


if __name__ == '__main__':
    unittest.main()
