"""SQLite transaction and durable cursor checks for bounded MaxPatrol polling."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from test_maxpatrol_storage import harness
from iris_maxpatrol_module.collector import SIEMError


NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
UUID1 = '00000006-050d-0642-f000-0000255d3663'
UUID2 = '00000006-050d-0642-f000-0000255d3664'
UUID3 = '00000006-050d-0642-f000-0000255d3665'


def configure(h, **values):
    row = h.db.session.get(h.Module, 1)
    row.module_config = row.module_config + [
        {'param_name': key, 'value': value} for key, value in values.items()]
    h.db.session.commit()
    h.config = h.business.configuration(row)


def state_for(h):
    state = h.models.MaxPatrolIngestState(source_key=h.config.source_key, incident_id='one',
        incident={'id': 'one', 'name': 'Original incident'}, cursor=None,
        deleted=False, legacy_migrated=False)
    h.db.session.add(state)
    h.db.session.commit()
    return state


def committing_alerts(h):
    def create(alert, **kwargs):
        h.db.session.add(alert)
        h.db.session.commit()
    h.alerts.alerts_create = create


def cursor(offset=1, done=False):
    return {'offset': offset, 'done': done, 'time_from': 1792584000,
            'time_to': 1792591200, 'page_size': 2, 'token': 'next'}


class PagesClient:
    def __init__(self, config, pages):
        self.config = config
        self.pages = iter(pages)
        self.last_response_bytes = 0
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((path, copy.deepcopy(kwargs)))
        self.last_response_bytes = 10
        if path == '/api/v2/incidents/':
            return {'incidents': []}
        page = next(self.pages)
        if isinstance(page, Exception):
            raise page
        return page


class IngestionTests(unittest.TestCase):
    def test_server_ignoring_limit_does_not_advance_or_discard_events(self):
        with harness() as h:
            configure(h, event_page_size=1)
            committing_alerts(h)
            state_for(h)
            client = PagesClient(h.config, [{'events': [{'uuid': UUID1}, {'uuid': UUID2}]}])
            h.ingestion.run_bounded_poll(h.config, client, 1, now=NOW)
            state = h.db.session.get(h.models.MaxPatrolIngestState, (h.config.source_key, 'one'))
            self.assertEqual(state.cursor['offset'], 0)
            self.assertEqual(state.cursor['last_error'], 'event_limit_ignored')
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 0)

    def test_page_commit_stores_full_events_once_and_compact_manifest(self):
        with harness() as h:
            committing_alerts(h)
            state = state_for(h)
            event = {'uuid': UUID1, 'body': 'raw payload' * 100, 'missing': None,
                     'historical': False, 'count': 0}
            self.assertTrue(h.ingestion.persist_page(h.config, 1, state, [event], cursor(), NOW))
            self.assertFalse(h.ingestion.persist_page(h.config, 1, state, [event], cursor(2, True), NOW))
            h.db.session.expire_all()
            alert = h.db.session.query(h.Alert).one()
            record = h.db.session.query(h.models.MaxPatrolEventRecord).one()
            self.assertEqual(record.payload['body'], event['body'])
            self.assertNotIn('missing', record.payload)
            self.assertIs(record.payload['historical'], False)
            self.assertEqual(record.payload['count'], 0)
            manifest = alert.alert_source_content
            self.assertNotIn('events', manifest)
            self.assertNotIn('raw payload', json.dumps(manifest))
            self.assertEqual(manifest['event_storage']['count'], 1)
            self.assertEqual(manifest['event_collection']['next_offset'], 2)
            self.assertTrue(manifest['event_collection']['pagination_complete'])
            self.assertFalse(manifest['event_collection']['complete'])
            self.assertFalse(manifest['event_collection']['linked_events_checked'])
            self.assertEqual(h.db.session.query(h.models.MaxPatrolReceipt).count(), 1)

    def test_failed_commit_rolls_back_events_receipt_alert_and_cursor(self):
        with harness() as h:
            committing_alerts(h)
            state = state_for(h)
            with patch.object(h.db.session, 'commit', side_effect=RuntimeError('commit unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'commit unavailable'):
                    h.ingestion.persist_page(h.config, 1, state, [{'uuid': UUID1}], cursor(), NOW)
            h.db.session.rollback()
            h.db.session.expire_all()
            self.assertEqual(h.db.session.query(h.Alert).count(), 0)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolReceipt).count(), 0)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 0)
            self.assertIsNone(h.db.session.get(h.models.MaxPatrolIngestState,
                (h.config.source_key, 'one')).cursor)

    def test_legacy_copy_preserves_raw_event_and_analyst_title_and_deduplicates(self):
        with harness() as h:
            committing_alerts(h)
            h.store.create('one', {'alert_title': 'Analyst title', 'alert_customer_id': 1,
                'alert_source': 'MaxPatrol SIEM', 'alert_source_ref': 'one',
                'alert_source_content': {'incident': {'id': 'one'}, 'custom': {'analyst': 'retained'},
                    'event_links': {UUID1: [UUID3]},
                    'events': [{'uuid': UUID1, 'body': 'original bytes', 'empty': None}],
                    'event_tree': [{'uuid': UUID1, 'event': {'uuid': UUID1, 'tree_extra': 'retained'}, 'subevents': [
                        {'uuid': UUID3, 'event': {'uuid': UUID3, 'body': 'tree-only raw'}}]}]}})
            state = state_for(h)
            self.assertFalse(h.ingestion.persist_page(h.config, 1, state,
                [{'uuid': UUID1, 'text': 'normalized'}, {'uuid': UUID2, 'body': 'new'}], cursor(2), NOW))
            h.db.session.expire_all()
            records = {row.event_key: row.payload for row in h.db.session.query(h.models.MaxPatrolEventRecord)}
            self.assertEqual(len(records), 3)
            self.assertEqual(records[UUID1]['body'], 'original bytes')
            self.assertEqual(records[UUID1]['text'], 'normalized')
            self.assertEqual(records[UUID1]['tree_extra'], 'retained')
            self.assertEqual(records[UUID3]['body'], 'tree-only raw')
            self.assertNotIn('empty', records[UUID1])
            alert = h.db.session.query(h.Alert).one()
            self.assertEqual(alert.alert_title, 'Analyst title')
            self.assertNotIn('events', alert.alert_source_content)
            self.assertNotIn('event_tree', alert.alert_source_content)
            self.assertEqual(alert.alert_source_content['custom'], {'analyst': 'retained'})
            self.assertEqual(alert.alert_source_content['event_links'], {UUID1: [UUID3]})
            self.assertTrue(state.legacy_migrated)

    def test_same_uuid_refresh_merges_new_values_and_retains_absent_raw_fields(self):
        with harness() as h:
            committing_alerts(h)
            state = state_for(h)
            h.ingestion.persist_page(h.config, 1, state,
                [{'uuid': UUID1, 'body': 'original raw', 'text': 'old'}], cursor(), NOW)
            h.ingestion.persist_page(h.config, 1, state,
                [{'uuid': UUID1, 'text': 'normalized', 'account': 'user'}], cursor(2), NOW)
            record = h.db.session.query(h.models.MaxPatrolEventRecord).one()
            self.assertEqual(record.payload, {'uuid': UUID1, 'body': 'original raw',
                'text': 'normalized', 'account': 'user'})

    def test_deleted_alert_leaves_receipt_and_marks_ingestion_tombstone(self):
        with harness() as h:
            committing_alerts(h)
            state = state_for(h)
            h.ingestion.persist_page(h.config, 1, state, [], cursor(0), NOW)
            h.db.session.delete(h.db.session.query(h.Alert).one())
            h.db.session.commit()
            self.assertFalse(h.ingestion.persist_page(h.config, 1, state,
                [{'uuid': UUID1}], cursor(), NOW))
            self.assertTrue(state.deleted)
            self.assertEqual(h.db.session.query(h.Alert).count(), 0)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolReceipt).count(), 1)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 0)

    def test_failed_legacy_conversion_keeps_original_materials_and_cursor(self):
        with harness() as h:
            committing_alerts(h)
            original = {'incident': {'id': 'one'}, 'events': [{'uuid': UUID1, 'body': 'legacy'}]}
            h.store.create('one', {'alert_title': 'Analyst title', 'alert_customer_id': 1,
                'alert_source': 'MaxPatrol SIEM', 'alert_source_ref': 'one',
                'alert_source_content': original})
            state = state_for(h)
            with patch.object(h.db.session, 'commit', side_effect=RuntimeError('commit unavailable')):
                with self.assertRaises(RuntimeError):
                    h.ingestion.persist_page(h.config, 1, state, [{'uuid': UUID2}], cursor(2), NOW)
            h.db.session.rollback()
            h.db.session.expire_all()
            self.assertEqual(h.db.session.query(h.Alert).one().alert_source_content, original)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 0)
            self.assertFalse(state.legacy_migrated)
            self.assertIsNone(state.cursor)

    def test_event_reader_returns_full_payload_in_disjoint_pages(self):
        with harness() as h:
            committing_alerts(h)
            state = state_for(h)
            h.ingestion.persist_page(h.config, 1, state,
                [{'uuid': UUID1, 'body': 'raw first'}, {'uuid': UUID2, 'body': 'raw second'}],
                cursor(2, True), NOW)
            alert = h.db.session.query(h.Alert).one()
            first = h.ingestion.list_alert_events(alert, limit=1)
            self.assertEqual(first['total'], 2)
            self.assertEqual(first['data'][0]['event']['body'], 'raw first')
            self.assertEqual(first['next_offset'], 1)
            self.assertTrue(first['has_more'])
            second = h.ingestion.list_alert_events(alert, offset=first['next_offset'], limit=1)
            self.assertEqual(second['data'][0]['event']['body'], 'raw second')
            self.assertIsNone(second['next_offset'])
            self.assertFalse(second['has_more'])

    def test_poll_resumes_saved_offset_token_and_frozen_window_after_restart(self):
        with harness() as h:
            configure(h, event_page_size=2)
            committing_alerts(h)
            state_for(h)
            first = PagesClient(h.config, [{'events': [{'uuid': UUID1}, {'uuid': UUID2}], 'token': 'page-token'}])
            self.assertEqual(h.ingestion.run_bounded_poll(h.config, first, 1, now=NOW), 1)
            event_call = first.calls[-1][1]
            self.assertEqual(event_call['params']['offset'], 0)
            h.db.session.close()
            second = PagesClient(h.config, [{'events': [], 'token': None}])
            self.assertEqual(h.ingestion.run_bounded_poll(h.config, second, 1,
                now=NOW + timedelta(seconds=h.config.interval + 1)), 0)
            resumed = second.calls[-1][1]
            self.assertEqual(resumed['params']['offset'], 2)
            self.assertEqual(resumed['params']['token'], 'page-token')
            self.assertEqual(resumed['body'], event_call['body'])
            state = h.db.session.get(h.models.MaxPatrolIngestState, (h.config.source_key, 'one'))
            self.assertTrue(state.cursor['done'])
            self.assertEqual(state.cursor['offset'], 2)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 2)

    def test_oversized_response_retries_same_offset_with_smaller_page_without_skipping(self):
        with harness() as h:
            configure(h, event_page_size=2)
            committing_alerts(h)
            state_for(h)
            first = PagesClient(h.config, [SIEMError('response too large', code='response_too_large')])
            self.assertEqual(h.ingestion.run_bounded_poll(h.config, first, 1, now=NOW), 1)
            state = h.db.session.get(h.models.MaxPatrolIngestState, (h.config.source_key, 'one'))
            self.assertEqual(state.cursor['offset'], 0)
            self.assertEqual(state.cursor['page_size'], 1)
            alert = h.db.session.query(h.Alert).one()
            self.assertEqual(alert.alert_source_content['event_collection']['errors'],
                             [{'reason': 'response_too_large'}])
            second = PagesClient(h.config, [{'events': [{'uuid': UUID1}]}])
            self.assertEqual(h.ingestion.run_bounded_poll(h.config, second, 1,
                now=NOW + timedelta(seconds=h.config.interval + 1)), 0)
            self.assertEqual(second.calls[-1][1]['params']['offset'], 0)
            self.assertEqual(second.calls[-1][1]['params']['limit'], 1)
            self.assertEqual(second.calls[-1][1]['body'], first.calls[-1][1]['body'])
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).one().event_key, UUID1)

    def test_expired_token_replays_frozen_window_without_duplicate_events(self):
        with harness() as h:
            configure(h, event_page_size=2)
            committing_alerts(h)
            state_for(h)
            page = {'events': [{'uuid': UUID1}, {'uuid': UUID2}], 'token': 'expired'}
            first = PagesClient(h.config, [page])
            h.ingestion.run_bounded_poll(h.config, first, 1, now=NOW)
            expired = PagesClient(h.config, [SIEMError('expired token', code='http_410')])
            h.ingestion.run_bounded_poll(h.config, expired, 1, now=NOW + timedelta(seconds=31))
            state = h.db.session.get(h.models.MaxPatrolIngestState, (h.config.source_key, 'one'))
            self.assertEqual(state.cursor['offset'], 0)
            self.assertIsNone(state.cursor['token'])
            replay = PagesClient(h.config, [page])
            h.ingestion.run_bounded_poll(h.config, replay, 1, now=NOW + timedelta(seconds=62))
            self.assertEqual(replay.calls[-1][1]['params']['offset'], 0)
            self.assertNotIn('token', replay.calls[-1][1]['params'])
            self.assertEqual(replay.calls[-1][1]['body'], first.calls[-1][1]['body'])
            self.assertEqual(state.cursor['offset'], 2)
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 2)

    def test_exhausted_event_budget_defers_other_incident_and_next_poll_serves_it(self):
        with harness() as h:
            configure(h, event_page_size=1, max_events_per_poll=1, max_incidents_per_poll=2)
            committing_alerts(h)
            state_for(h)
            h.db.session.add(h.models.MaxPatrolIngestState(source_key=h.config.source_key,
                incident_id='two', incident={'id': 'two'}, deleted=False, legacy_migrated=False))
            h.db.session.commit()
            first = PagesClient(h.config, [{'events': [{'uuid': UUID1}]}])
            h.ingestion.run_bounded_poll(h.config, first, 1, now=NOW)
            event_calls = [kwargs for path, kwargs in first.calls if path == '/api/events/v3/events/']
            self.assertEqual(len(event_calls), 1)
            self.assertEqual(event_calls[0]['params']['incidentId'], 'one')
            second = PagesClient(h.config, [{'events': [{'uuid': UUID2}]}])
            h.ingestion.run_bounded_poll(h.config, second, 1, now=NOW + timedelta(seconds=1))
            self.assertEqual(second.calls[-1][1]['params']['incidentId'], 'two')
            self.assertEqual(h.db.session.query(h.models.MaxPatrolEventRecord).count(), 2)

    def test_postgresql_migration_is_additive_and_declares_single_copy_event_storage(self):
        path = Path(__file__).resolve().parents[1] / 'source/app/alembic/versions/utmn_maxpatrol02.py'
        spec = importlib.util.spec_from_file_location('bounded_maxpatrol_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        output = io.StringIO()
        context = MigrationContext.configure(dialect_name='postgresql',
            opts={'as_sql': True, 'output_buffer': output})
        with Operations.context(context):
            migration.upgrade()
        sql = output.getvalue()
        self.assertIn('CREATE TABLE maxpatrol_ingest_state', sql)
        self.assertIn('CREATE TABLE maxpatrol_event_record', sql)
        self.assertIn('payload JSONB NOT NULL', sql)
        self.assertIn('PRIMARY KEY (source_key, incident_id, event_key)', sql)
        self.assertIn('ON DELETE CASCADE', sql)
        self.assertNotIn('DROP ', sql)
        self.assertNotIn('DELETE FROM ', sql)

    def test_postgresql_upsert_compiles_jsonb_merge_and_size_recalculation(self):
        with harness() as h:
            state_for(h)
            state = types.SimpleNamespace(source_key=h.config.source_key, incident_id='one')
            from uuid import uuid4
            alert = types.SimpleNamespace(alert_uuid=uuid4())
            pg_engine = types.SimpleNamespace(dialect=postgresql.dialect())
            with patch.object(h.db, 'engine', pg_engine), patch.object(h.db.session, 'execute') as execute:
                h.ingestion._upsert_event(state, alert, {'uuid': UUID1, 'body': 'raw'})
            statement = execute.call_args.args[0]
            sql = str(statement.compile(dialect=postgresql.dialect()))
            self.assertIn('ON CONFLICT (source_key, incident_id, event_key) DO UPDATE', sql)
            self.assertIn('maxpatrol_event_record.payload || excluded.payload', sql)
            self.assertIn('octet_length', sql)


if __name__ == '__main__':
    unittest.main()
