"""Execute the legacy transfer on PostgreSQL; use temporary tables only.

Set MAXPATROL_TEST_POSTGRES_URL to a disposable PostgreSQL database URL
(postgresql+psycopg://...). Without it these integration tests are skipped.
"""
import json
import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, text

from test_maxpatrol_storage import harness


@unittest.skipUnless(os.environ.get('MAXPATROL_TEST_POSTGRES_URL'), 'PostgreSQL test URL not configured')
class LegacyPostgreSQLTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['MAXPATROL_TEST_POSTGRES_URL'])
        self.addCleanup(self.engine.dispose)
        self.connection = self.engine.connect()
        self.addCleanup(self.connection.close)
        self.transaction = self.connection.begin()
        self.addCleanup(self.transaction.rollback)
        self.connection.execute(text('CREATE TEMP TABLE alerts ('
            'alert_uuid uuid PRIMARY KEY, alert_source_content json) ON COMMIT DROP'))
        self.connection.execute(text('CREATE TEMP TABLE maxpatrol_event_record ('
            'source_key varchar(64), incident_id varchar(512), event_key varchar(80), '
            'alert_uuid uuid, payload jsonb NOT NULL, byte_size integer NOT NULL, '
            'PRIMARY KEY (source_key, incident_id, event_key)) ON COMMIT DROP'))
        with harness() as h:
            self.sql = h.ingestion.LEGACY_COPY_SQL

    def transfer(self, content):
        alert_uuid = uuid4()
        self.connection.execute(text('INSERT INTO alerts VALUES (:uuid, CAST(:content AS json))'),
            {'uuid': alert_uuid, 'content': json.dumps(content)})
        parameters = {'source_key': 'test-source', 'incident_id': 'one', 'alert_uuid': str(alert_uuid)}
        self.connection.execute(text(self.sql), parameters)
        return alert_uuid, parameters

    def test_empty_new_alert_does_not_fail_or_insert_placeholder(self):
        self.transfer({})
        self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_event_record')).scalar(), 0)

    def test_flat_and_tree_events_merge_without_loss_and_replay_is_idempotent(self):
        first, second = str(uuid4()), str(uuid4())
        content = {'events': [{'uuid': first, 'body': 'original raw', 'text': 'old', 'empty': None}],
            'event_tree': [{'uuid': first, 'event': {'uuid': first, 'text': 'richer', 'flag': False},
                'subevents': [{'uuid': second, 'event': {'uuid': second, 'body': 'tree only', 'count': 0}}]}]}
        alert_uuid, parameters = self.transfer(content)
        self.connection.execute(text(self.sql), parameters)
        rows = self.connection.execute(text('SELECT event_key, payload, byte_size, '
            'octet_length(payload::text) FROM maxpatrol_event_record')).all()
        self.assertEqual(len(rows), 2)
        payloads = {key: payload for key, payload, _, _ in rows}
        self.assertEqual(payloads[first], {'uuid': first, 'body': 'original raw', 'text': 'richer', 'flag': False})
        self.assertEqual(payloads[second], {'uuid': second, 'body': 'tree only', 'count': 0})
        self.assertTrue(all(size == actual for _, _, size, actual in rows))
        # The transfer itself must leave the source intact until the caller commits the manifest.
        original = self.connection.execute(text('SELECT alert_source_content FROM alerts WHERE alert_uuid=:id'),
            {'id': alert_uuid}).scalar()
        self.assertEqual(original, content)

    def test_wrong_type_flat_array_and_unrelated_alert_are_ignored(self):
        self.connection.execute(text('INSERT INTO alerts VALUES (:uuid, CAST(:content AS json))'),
            {'uuid': uuid4(), 'content': json.dumps({'events': [{'uuid': str(uuid4()), 'body': 'other alert'}]})})
        self.transfer({'events': None, 'event_tree': []})
        self.assertEqual(self.connection.execute(text('SELECT count(*) FROM maxpatrol_event_record')).scalar(), 0)
