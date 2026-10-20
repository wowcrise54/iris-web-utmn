"""Offline contract tests; no SIEM, broker, or application boot required."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone

SOURCE = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0, str(SOURCE))


class MaxPatrolTests(unittest.TestCase):
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

    def test_events_pagination_cleanup_and_payload(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client = m.Client(c)
        client.request = Mock(side_effect=[{'events': [{'n': n} for n in range(250)]},
                                           {'events': [{'body': 'event', 'empty': None}]}])
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        events = client.events('a/b', now, now)
        self.assertEqual(len(events), 251)
        self.assertEqual(events[-1], {'body': 'event'})
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
        client.detail.side_effect = [m.SIEMError('unavailable'), {'name': 'Two'}, {'name': 'One'}]
        client.events.return_value = []
        processed = set()
        store = Mock()
        store.active.return_value = True
        store.seen.side_effect = lambda incident_id: incident_id in processed
        store.create.side_effect = lambda incident_id, _payload: processed.add(incident_id)
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertEqual(m.collect(c, client, store, now=now), 1)
        self.assertEqual(processed, {'two'})
        self.assertEqual(m.collect(c, client, store, now=now), 1)
        self.assertEqual(processed, {'one', 'two'})
        self.assertEqual(store.create.call_count, 2)

    def test_events_failure_still_creates_alert_and_disable_stops_work(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one'}, {'id': 'two'}]
        client.detail.return_value = {'name': 'One'}
        client.events.side_effect = m.SIEMError('events unavailable')
        store.active.side_effect = [True, False]
        store.seen.return_value = False
        self.assertEqual(m.collect(c, client, store), 1)
        self.assertEqual(store.create.call_args.args[1]['alert_source_content']['events'], [])
        self.assertEqual(client.detail.call_count, 1)

    def test_create_failure_is_not_success_and_does_not_stop_other_incidents(self):
        m = self.core()
        c = m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'x'})
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one'}, {'id': 'two'}]
        client.detail.return_value = {'name': 'Incident'}
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
        client.detail.return_value = {'name': 'One'}
        client.events.return_value = []
        store.active.return_value = True
        store.seen.side_effect = [False, True, True]
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
            client.detail('a/b')
        kwargs = session.request.call_args.kwargs
        self.assertTrue(kwargs['verify'])
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['timeout'], 60)
        self.assertFalse(session.trust_env)
        self.assertTrue(session.request.call_args.args[1].endswith('/a%2Fb'))

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


if __name__ == '__main__':
    unittest.main()
