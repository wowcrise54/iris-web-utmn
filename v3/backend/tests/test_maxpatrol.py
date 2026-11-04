"""Offline contract tests; no SIEM, broker, or application boot required."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone
from requests import Response

SOURCE = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0, str(SOURCE))


class MaxPatrolTests(unittest.TestCase):
    def test_null_cleanup_reuses_shared_event_data_without_mutating_input(self):
        m = self.core()
        event = {'body': 'original', 'empty': None, 'nested': {'count': 0, 'empty': None}}
        content = {'events': [event], 'event_tree': [{'event': event}, {'event': event}]}
        cleaned = m.without_null_fields(content)
        self.assertEqual(cleaned['events'][0], {'body': 'original', 'nested': {'count': 0}})
        self.assertIs(cleaned['events'][0], cleaned['event_tree'][0]['event'])
        self.assertIs(cleaned['events'][0], cleaned['event_tree'][1]['event'])
        self.assertIn('empty', event)
        self.assertIn('empty', event['nested'])

    def test_http_json_is_cleaned_before_any_incident_or_event_processing(self):
        m = self.core()
        response = Response()
        response.status_code = 200
        response._content = (b'{"errors":null,"events":[{"uuid":"test","empty":null,'
            b'"nested":{"empty":null,"flag":false,"count":0,"text":""},'
            b'"items":[null,{"empty":null,"keep":1}],"body":"{\\"raw\\":null}"}]}')
        session = Mock()
        session.request.return_value = response
        config = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'secret'})
        result = m.Client(config, session).request('POST', '/api/events/v3/events/')
        self.assertNotIn('errors', result)
        self.assertEqual(result['events'][0], {'uuid': 'test',
            'nested': {'flag': False, 'count': 0, 'text': ''},
            'items': [None, {'keep': 1}], 'body': '{"raw":null}'})

    def core(self):
        path = SOURCE / 'iris_maxpatrol_module' / 'collector.py'
        self.assertTrue(path.exists(), 'MaxPatrol collector is missing')
        spec = importlib.util.spec_from_file_location('maxpatrol_collector', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_config_defaults_tls_and_validation(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local/', 'api_token': 'secret'})
        self.assertEqual((c.interval, c.lookback_hours, c.verify_tls), (30, 72, True))
        self.assertEqual(c.url, 'https://siem.local')
        self.assertNotIn('secret', repr(c))
        for extra in ({'siem_url': 'http://siem.local'}, {'interval': '0'},
                      {'verify_tls': 'nope'}, {'customer_id': True},
                      {'api_token': 'bad\nheader'}, {'siem_url': 'https://u:p@siem.local'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'secret', **extra})
        self.assertFalse(m.Config.from_values({'siem_url': 'https://siem.local',
                                             'api_token': 'secret', 'verify_tls': 'false'}).verify_tls)

    def test_incident_pagination_fixed_window(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client = m.Client(c)
        client.request = Mock(side_effect=[{'incidents': [{'id': str(n)} for n in range(50)]},
                                           {'incidents': [{'id': 'last'}]}])
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        result = list(client.incidents(now, now))
        self.assertEqual(len(result), 51)
        calls = client.request.call_args_list
        self.assertEqual([call.kwargs['body']['offset'] for call in calls], [0, 50])
        self.assertEqual(calls[0].kwargs['body']['timeTo'], calls[1].kwargs['body']['timeTo'])

    def test_poll_caps_saved_lookback_and_preserves_existing_incident_refresh(self):
        m = self.core()
        now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        for hours, expected_start in (
                ('72', datetime(2026, 10, 19, 12, tzinfo=timezone.utc)),
                ('24', datetime(2026, 10, 19, 12, tzinfo=timezone.utc)),
                ('12', datetime(2026, 10, 20, tzinfo=timezone.utc)),
                ('1', datetime(2026, 10, 20, 11, tzinfo=timezone.utc))):
            with self.subTest(lookback_hours=hours):
                config = m.Config.from_values({'siem_url': 'https://siem.local',
                    'api_token': 'x', 'lookback_hours': hours, 'interval': '120'})
                client, store = Mock(), Mock()
                client.incidents.return_value = [{'id': 'existing'}]
                client.events.return_value = []
                store.active.return_value = True
                store.seen.return_value = True
                store.needs_event_refresh.return_value = True
                store.stored_incident.return_value = {'id': 'existing', 'created': '2026-10-20T11:30:00Z'}

                self.assertEqual(m.collect(config, client, store, now=now), 0)

                client.incidents.assert_called_once_with(expected_start, now)
                client.events.assert_called_once_with('existing', expected_start, now)
                self.assertEqual(config.interval, 120)
                store.needs_event_refresh.assert_called_once_with('existing')
                store.refresh_events.assert_called_once()
                store.create.assert_not_called()

    def test_events_pagination_cleanup_and_payload(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client = m.Client(c)
        client.request = Mock(side_effect=[{'events': [{'n': n} for n in range(250)]},
                                           {'events': [{'body': 'event', 'empty': None}]}])
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        events = client.events('a/b', now, now)
        self.assertEqual(len(events), 251)
        self.assertEqual(events[-1], {'body': 'event', 'empty': None})
        self.assertEqual(client.request.call_args_list[1].kwargs['params']['offset'], 250)
        payload = m.alert_payload(c, 'a/b', {'name': 'Test', 'created': '2026-10-19T10:00:00Z'}, events, now)
        self.assertEqual(payload['alert_source_ref'], 'a/b')
        self.assertEqual(payload['alert_source_content']['events'], events)
        self.assertTrue(payload['alert_source_link'].endswith('/a%2Fb'))
        self.assertEqual(payload['alert_source_event_time'], datetime(2026, 10, 19, 10))
        self.assertEqual((payload['alert_severity_id'], payload['alert_status_id']), (1, 5))

    def test_retry_failed_incident_and_skip_success_after_restart(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client = Mock()
        client.incidents.return_value = [{'id': 'one'}, {'id': 'two'}]
        client.events.return_value = []
        processed = set()
        store = Mock()
        store.active.return_value = True
        store.seen.side_effect = lambda incident_id: incident_id in processed
        store.needs_event_refresh.return_value = False
        failed_once = set()

        def create(incident_id, _payload):
            if incident_id == 'one' and incident_id not in failed_once:
                failed_once.add(incident_id)
                raise RuntimeError('temporary database failure')
            processed.add(incident_id)

        store.create.side_effect = create
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertEqual(m.collect(c, client, store, now=now), 1)
        self.assertEqual(processed, {'two'})
        self.assertEqual(m.collect(c, client, store, now=now), 1)
        self.assertEqual(processed, {'one', 'two'})
        self.assertEqual(store.create.call_count, 3)

    def test_events_failure_still_creates_alert_and_disable_stops_work(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one'}, {'id': 'two'}]
        client.events.side_effect = m.SIEMError('events unavailable')
        store.active.side_effect = [True, False]
        store.seen.return_value = False
        self.assertEqual(m.collect(c, client, store), 1)
        self.assertEqual(store.create.call_args.args[1]['alert_source_content']['events'], [])
        self.assertEqual(client.events.call_count, 1)

    def test_create_failure_is_not_success_and_does_not_stop_other_incidents(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one'}, {'id': 'two'}]
        client.events.return_value = []
        store.active.return_value = True
        store.seen.return_value = False
        store.create.side_effect = [RuntimeError('db unavailable'), None]
        self.assertEqual(m.collect(c, client, store), 1)
        store.rollback.assert_called_once()

    def test_failure_after_commit_counts_persisted_alert_once(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one'}]
        client.events.return_value = []
        store.active.return_value = True
        store.seen.side_effect = [False, True, True]
        store.needs_event_refresh.return_value = False
        store.create.side_effect = RuntimeError('hook failed after commit')
        self.assertEqual(m.collect(c, client, store), 1)
        self.assertEqual(m.collect(c, client, store), 0)
        store.create.assert_called_once()

    def test_request_uses_tls_and_does_not_leak_server_error(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'secret'})
        session = Mock()
        session.request.return_value.status_code = 302
        session.request.return_value.text = 'private server response'
        client = m.Client(c, session)
        with self.assertRaisesRegex(m.SIEMError, '^MaxPatrol HTTP 302$'):
            client.request('POST', '/api/events/v3/events/')
        kwargs = session.request.call_args.kwargs
        self.assertTrue(kwargs['verify'])
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['timeout'], 60)
        self.assertFalse(session.trust_env)
        self.assertTrue(session.request.call_args.args[1].endswith('/api/events/v3/events/'))

    def test_repeating_full_pages_and_invalid_responses_fail(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client = m.Client(c)
        now = datetime.now(timezone.utc)
        client.request = Mock(return_value={'incidents': [{'id': str(n)} for n in range(50)]})
        with self.assertRaisesRegex(m.SIEMError, 'advance'):
            list(client.incidents(now, now))
        client.request = Mock(return_value={'incidents': None})
        with self.assertRaises(m.SIEMError):
            list(client.incidents(now, now))

    def test_info_logs_distinguish_received_imported_duplicates_and_errors(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'private-token'})
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'old'}, {'id': 'new'}, {'id': 'bad'}, {}]
        client.events.return_value = [{'body': 'private-body'}]
        store.active.return_value = True
        store.seen.side_effect = lambda incident_id: incident_id == 'old'
        store.needs_event_refresh.return_value = False
        store.create.side_effect = [None, RuntimeError('private response')]
        with self.assertLogs(m.log, level='INFO') as captured:
            self.assertEqual(m.collect(c, client, store), 1)
        output = '\n'.join(captured.output)
        self.assertIn('MaxPatrol collection started:', output)
        self.assertIn('MaxPatrol incident imported:', output)
        self.assertIn('received=4 created=1 already_imported=1 failed=1 invalid=1', output)
        self.assertIn('complete=True', output)
        for secret in ('private-token', 'private-title', 'private-body', 'private response'):
            self.assertNotIn(secret, output)

    def test_empty_response_is_visible_at_info(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client = m.Client(c)
        client.request = Mock(return_value={'incidents': []})
        with self.assertLogs(m.log, level='INFO') as captured:
            self.assertEqual(m.collect(c, client, Mock()), 0)
        output = '\n'.join(captured.output)
        self.assertIn('MaxPatrol incidents page received: offset=0 count=0', output)
        self.assertIn('received=0 created=0 already_imported=0 failed=0 invalid=0', output)
        self.assertIn('complete=True', output)

    def test_list_failure_has_incomplete_summary_and_safe_reason(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        session = Mock()
        session.request.return_value.status_code = 401
        client = m.Client(c, session)
        with self.assertLogs(m.log, level='INFO') as captured, self.assertRaises(m.SIEMError) as error:
            m.collect(c, client, Mock())
        self.assertEqual(error.exception.code, 'http_401')
        self.assertIn('complete=False', '\n'.join(captured.output))

    def test_transport_errors_have_safe_diagnostic_codes(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'private-token'})
        for error, expected in ((m.requests.exceptions.SSLError, 'tls_error'),
                                (m.requests.exceptions.Timeout, 'timeout'),
                                (m.requests.exceptions.ConnectionError, 'connection_error')):
            session = Mock()
            session.request.side_effect = error('private-token in underlying error')
            with self.subTest(expected=expected), self.assertRaises(m.SIEMError) as result:
                m.Client(c, session).request('POST', '/api/events/v3/events/')
            self.assertEqual(result.exception.code, expected)
            self.assertNotIn('private-token', str(result.exception))


if __name__ == '__main__':
    unittest.main()
