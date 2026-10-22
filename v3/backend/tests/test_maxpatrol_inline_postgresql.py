"""Execute the inline rollback migration on disposable PostgreSQL temporary tables."""
import importlib.util
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


@unittest.skipUnless(os.environ.get('MAXPATROL_TEST_POSTGRES_URL'), 'PostgreSQL test URL not configured')
class InlineMigrationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'source/app/alembic/versions/utmn_maxpatrol03.py'
        spec = importlib.util.spec_from_file_location('maxpatrol_inline_migration', path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        engine = create_engine(os.environ['MAXPATROL_TEST_POSTGRES_URL'])
        self.addCleanup(engine.dispose)
        self.connection = engine.connect()
        self.addCleanup(self.connection.close)
        transaction = self.connection.begin()
        self.addCleanup(transaction.rollback)
        for sql in (
            'CREATE TEMP TABLE alerts (alert_uuid uuid PRIMARY KEY, alert_source text, alert_source_content json)',
            'CREATE TEMP TABLE maxpatrol_event_record (alert_uuid uuid, event_key text, payload jsonb)',
            'CREATE TEMP TABLE iris_module (module_name text, module_config json)',
        ):
            self.connection.execute(text(sql))
        # Migration-created archive tables must also remain in this temporary schema.
        self.connection.execute(text('SET LOCAL search_path TO pg_temp'))

    def upgrade(self):
        with Operations.context(MigrationContext.configure(self.connection)):
            self.migration.upgrade()

    def add_alert(self, content):
        uid = uuid4()
        self.connection.execute(text('INSERT INTO alerts VALUES (:id, :source, CAST(:content AS json))'),
            {'id': uid, 'source': 'MaxPatrol SIEM', 'content': json.dumps(content)})
        return uid

    def test_restores_events_and_preserves_evidence_and_unrelated_configuration(self):
        uid = self.add_alert({'incident': {'id': 'one'}, 'custom': 'retained',
            'event_storage': {'kind': 'maxpatrol'}, 'event_collection': {'version': 3}})
        event = {'uuid': str(uuid4()), 'empty': None, 'nested': {'remove': None, 'keep': False},
                 'count': 0, 'body': '{"original":null}'}
        self.connection.execute(text('INSERT INTO maxpatrol_event_record VALUES (:id, :key, CAST(:payload AS jsonb))'),
            {'id': uid, 'key': event['uuid'], 'payload': json.dumps(event)})
        config = [{'param_name': 'api_token', 'value': 'encrypted-test'},
                  {'param_name': 'max_events_per_poll', 'value': '100'},
                  {'param_name': 'custom_setting', 'value': False}]
        self.connection.execute(text('INSERT INTO iris_module VALUES (:name, CAST(:config AS json))'),
            {'name': 'iris_maxpatrol_module', 'config': json.dumps(config)})
        self.upgrade()
        saved = self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': uid}).scalar()
        self.assertEqual(saved['custom'], 'retained')
        self.assertNotIn('event_storage', saved)
        self.assertEqual(saved['events'], [{'uuid': event['uuid'], 'nested': {'keep': False},
                                         'count': 0, 'body': '{"original":null}'}])
        self.assertEqual(saved['event_collection']['version'], 2)
        self.assertFalse(saved['event_collection']['complete'])
        self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_event_record')).scalar(), 1)
        self.assertEqual(self.connection.execute(text('SELECT module_config FROM iris_module')).scalar(),
                         [config[0], config[2]])
        self.upgrade()
        self.assertEqual(self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': uid}).scalar(), saved)

    def test_empty_manifest_is_restored_but_existing_inline_alert_is_untouched(self):
        empty = self.add_alert({'event_storage': {'kind': 'maxpatrol'}, 'incident': {'id': 'empty'}})
        original = {'events': [{'body': 'existing evidence'}], 'custom': False}
        inline = self.add_alert(original)
        self.upgrade()
        self.assertEqual(self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': empty}).scalar()['events'], [])
        self.assertEqual(self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': inline}).scalar(), original)

    def test_large_archive_is_not_aggregated_into_the_alert_or_deleted(self):
        uid = self.add_alert({'incident': {'id': 'large'}, 'custom': 'retained',
                             'event_storage': {'kind': 'maxpatrol'}})
        self.connection.execute(text("INSERT INTO maxpatrol_event_record "
            "SELECT :id, n::text, jsonb_build_object('body', repeat('x', 1048576)) "
            "FROM generate_series(1, 9) n"), {'id': uid})
        self.upgrade()
        saved = self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': uid}).scalar()
        self.assertFalse('events' in saved, 'oversized archive must not be inlined')
        self.assertEqual(saved['custom'], 'retained')
        self.assertTrue(saved['event_storage']['archived_only'])
        self.assertEqual(saved['event_storage']['count'], 9)
        self.assertTrue(saved['event_collection']['refresh_blocked'])
        self.assertFalse(saved['event_collection']['complete'])
        self.assertLess(len(json.dumps(saved)), 4096)
        self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_event_record')).scalar(), 9)
        self.upgrade()
        self.assertEqual(self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': uid}).scalar(), saved)

    def test_archive_over_postgresql_jsonb_container_limit_does_not_block_startup(self):
        uid = self.add_alert({'event_storage': {'kind': 'maxpatrol'}})
        # Generated in PostgreSQL: no 256+ MiB fixture or aggregate in the test process.
        self.connection.execute(text("INSERT INTO maxpatrol_event_record "
            "SELECT :id, n::text, jsonb_build_object('body', repeat('x', 65536)) "
            "FROM generate_series(1, 4200) n"), {'id': uid})
        self.upgrade()
        saved = self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': uid}).scalar()
        self.assertGreater(saved['event_storage']['bytes'], 268435455)
        self.assertEqual(saved['event_storage']['count'], 4200)
        self.assertTrue(saved['event_collection']['refresh_blocked'])
        self.assertNotIn('events', saved)
        self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_event_record')).scalar(), 4200)

    def test_oversized_source_json_is_preserved_without_casting_it_to_jsonb(self):
        for mib in (226, 418):
            with self.subTest(mib=mib):
                uid = uuid4()
                # Construct a large plain JSON value in PostgreSQL, never in Python or JSONB.
                self.connection.execute(text("INSERT INTO alerts VALUES (:id, 'MaxPatrol SIEM', "
                    "('{\"event_storage\":{\"kind\":\"maxpatrol\"},\"body\":\"' || "
                    "repeat('x', :bytes) || '\"}')::json)"), {'id': uid, 'bytes': mib * 1024 * 1024})
                size, digest = self.connection.execute(text('SELECT octet_length(alert_source_content::text), '
                    'md5(alert_source_content::text) FROM alerts WHERE alert_uuid=:id'), {'id': uid}).one()
                self.upgrade()
                saved = self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
                    {'id': uid}).scalar()
                self.assertTrue(saved['event_collection']['refresh_blocked'])
                self.assertLess(len(json.dumps(saved)), 4096)
                archive_id = saved['event_storage']['payload_archive_id']
                archived = self.connection.execute(text('SELECT alert_uuid, payload_bytes, '
                    'octet_length(payload::text), md5(payload::text) FROM maxpatrol_payload_archive '
                    'WHERE archive_id=:id'), {'id': archive_id}).one()
                self.assertEqual(archived, (uid, size, size, digest))
                count = self.connection.execute(text('SELECT count(*) FROM maxpatrol_payload_archive')).scalar()
                self.upgrade()
                self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_payload_archive')).scalar(), count)

    def test_large_source_without_storage_marker_is_archived_before_json_inspection(self):
        uid = self.add_alert({'body': 'x' * (9 * 1024 * 1024)})
        self.upgrade()
        saved = self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': uid}).scalar()
        self.assertTrue(saved['event_storage']['payload_archive_id'] > 0)
        self.assertTrue(saved['event_collection']['refresh_blocked'])

    def test_rolled_back_transfer_preserves_source_and_can_be_retried(self):
        uid = self.add_alert({'body': 'x' * (9 * 1024 * 1024)})
        original = self.connection.execute(text('SELECT md5(alert_source_content::text) '
            'FROM alerts WHERE alert_uuid=:id'), {'id': uid}).scalar()
        savepoint = self.connection.begin_nested()
        self.upgrade()
        savepoint.rollback()
        self.assertEqual(self.connection.execute(text('SELECT md5(alert_source_content::text) '
            'FROM alerts WHERE alert_uuid=:id'), {'id': uid}).scalar(), original)
        self.upgrade()
        self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_payload_archive')).scalar(), 1)
