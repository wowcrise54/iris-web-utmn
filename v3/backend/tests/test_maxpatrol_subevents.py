"""Tree assembly and captured v3 request contract, without guessed event APIs."""
from unittest.mock import Mock
import unittest

import test_maxpatrol as base_tests

A = '00000006-050d-0642-f000-0000255d3663'
B = '00000006-050d-0642-f000-0000255d3664'
C = '00000006-050d-0642-f000-0000255d3665'
T = '2020-01-01T10:00:00.0000000Z'


def event(uid, children=(), **fields):
    return {'uuid': uid, 'time': T, 'id': 'same_normalizer', 'normalized': True,
            'subevents': list(children), 'count.subevents': len(children), **fields}


class SubeventTests(unittest.TestCase):
    def assert_reference_tree(self, nodes):
        for node in nodes:
            self.assertNotIn('event', node, 'Raw events must only live in the flat event collection')
            self.assertTrue(set(node) <= {'uuid', 'subevents', 'reference', 'missing'})
            self.assert_reference_tree(node.get('subevents', []))

    def setUp(self):
        self.m = base_tests.MaxPatrolTests().core()
        self.config = self.m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'secret'})
        self.client = self.m.Client(self.config)

    def test_nested_shared_children_cycles_and_same_normalizer_are_preserved(self):
        rows = [event(A, [B, C]), event(B, [C]), event(C, [A], body='raw child')]
        result = self.m.build_event_materials(rows)
        self.assertEqual({row['uuid'] for row in result['events']}, {A, B, C})
        self.assertTrue(result['event_collection']['complete'])
        tree = result['event_tree'][0]
        self.assertEqual(tree['uuid'], A)
        self.assertEqual(tree['subevents'][0]['uuid'], B)
        self.assertTrue(tree['subevents'][0]['subevents'][0]['subevents'][0]['reference'])

    def test_missing_events_are_explicit_and_successful_children_survive(self):
        result = self.m.build_event_materials([event(A, [B, C]), event(B, body='retained')])
        self.assertFalse(result['event_collection']['complete'])
        self.assertIn(C, result['event_collection']['missing_uuids'])
        self.assertEqual(len(result['events']), 2)

    def test_uuid_from_meta_supported_without_extra_api(self):
        result = self.m.build_event_materials([{'_meta': {'id': A}}])
        self.assertTrue(result['event_collection']['complete'])
        self.assertEqual(result['event_tree'][0]['uuid'], A)

    def test_collect_saves_expanded_materials_and_refreshes_existing_alert(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'incident'}]
        client.events.return_value = [event(A, [B]), event(B, body='raw child')]
        store.active.return_value = True
        store.seen.return_value = True
        store.needs_event_refresh.return_value = True
        self.assertEqual(self.m.collect(self.config, client, store), 0)
        store.create.assert_not_called()
        content = store.refresh_events.call_args.args[1]
        self.assertEqual({row['uuid'] for row in content['events']}, {A, B})
        self.assertTrue(content['event_collection']['complete'])

    def test_malformed_child_ids_do_not_claim_complete(self):
        self.assertFalse(self.m.build_event_materials([event(A, ['not-a-uuid'])])['event_collection']['complete'])

    def test_refresh_outside_incident_discovery_window(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = []
        client.events.return_value = []
        store.active.return_value = True
        store.seen.return_value = True
        store.needs_event_refresh.return_value = True
        self.m.collect(self.config, client, store, extra_incidents=['old', 'old'])
        store.refresh_events.assert_called_once()

    def test_client_contract_to_alert_keeps_old_child_raw_and_normalized_fields(self):
        self.client.incidents = Mock(return_value=[{'id': 'incident'}])
        self.client.request = Mock(return_value={'errors': None, 'events': [
            event(B, body='<Event>original</Event>', mime='text/xml',
                  custom={'process': {'name': 'example'}}), event(A, [B])], 'token': 'page-token'})
        store = Mock()
        store.active.return_value = True
        store.seen.return_value = False
        self.assertEqual(self.m.collect(self.config, self.client, store), 1)
        content = store.create.call_args.args[1]['alert_source_content']
        self.assertEqual(len(content['events']), 2)
        child_ref = content['event_tree'][0]['subevents'][0]
        child = next(row for row in content['events'] if row['uuid'] == child_ref['uuid'])
        self.assert_reference_tree(content['event_tree'])
        self.assertEqual(child['body'], '<Event>original</Event>')
        self.assertEqual(child['custom']['process']['name'], 'example')
        self.assertTrue(content['event_collection']['complete'])
        body = self.client.request.call_args_list[0].kwargs['body']
        self.assertGreater(body['timeFrom'], 0)
        self.assertEqual(body['timeTo'] - body['timeFrom'], 72 * 3600)
        self.assertEqual(self.client.request.call_count, 1)

    def test_v3_full_response_builds_tree_without_detail_or_subevent_requests(self):
        rows = [event(B, body='{"Event":{"Data":[]}}', **{'count.subevents': None,
            '_checkpoint': 123, '_presentation': [], '_whitelisting': None}),
            event(A, [B], **{'count.subevents': None})]
        result = self.m.build_event_materials(rows)
        self.assertTrue(result['event_collection']['complete'])
        self.assertEqual(len(result['event_tree']), 1)
        self.assertEqual(result['event_tree'][0]['uuid'], A)
        child_ref = result['event_tree'][0]['subevents'][0]
        child = next(row for row in result['events'] if row['uuid'] == child_ref['uuid'])
        self.assert_reference_tree(result['event_tree'])
        self.assertEqual(child['_presentation'], [])
        self.assertIsNone(child['_whitelisting'])
        self.assertEqual(child['body'], rows[0]['body'])

    def test_v3_query_is_pdql_and_carries_token_between_pages(self):
        self.client.request = Mock(side_effect=[{'errors': None, 'events': [event(A)] * 250, 'token': 'page-token'},
                                               {'errors': None, 'events': []}])
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        self.client.events('incident', now, now)
        first, second = self.client.request.call_args_list
        self.assertEqual(first.args, ('POST', '/api/events/v3/events/'))
        self.assertIsInstance(first.kwargs['body']['filter'], str)
        self.assertIn('_checkpoint,', first.kwargs['body']['filter'])
        self.assertIn('object.process.system_id', first.kwargs['body']['filter'])
        self.assertEqual(first.kwargs['params']['incidentId'], 'incident')
        self.assertEqual(second.kwargs['params']['token'], 'page-token')

    def test_http_request_matches_supplied_working_postman_contract(self):
        from datetime import datetime, timezone
        from pathlib import Path
        expected = (Path(__file__).parent / 'fixtures/maxpatrol_v3_select.txt').read_text(encoding='utf-8').strip()
        session = Mock()
        session.request.return_value = base_tests.streaming_response(
            200, b'{"errors":null,"events":[],"token":null}')
        client = self.m.Client(self.config, session)
        client.events(A, datetime.fromtimestamp(1792486213, timezone.utc),
                      datetime.fromtimestamp(1792486218, timezone.utc))
        call = session.request.call_args
        self.assertEqual(call.args, ('POST', 'https://siem.local/api/events/v3/events/'))
        self.assertEqual(call.kwargs['params'], {'incidentId': A, 'offset': 0, 'limit': 250, 'noCount': 'true'})
        self.assertEqual(call.kwargs['headers']['Content-Type'], 'application/json')
        self.assertEqual(call.kwargs['headers']['Accept-Encoding'], 'identity')
        self.assertTrue(call.kwargs['stream'])
        self.assertEqual(call.kwargs['json'], {'filter': expected, 'timeFrom': 1792486213, 'timeTo': 1792486218})

    def test_old_incident_refresh_uses_bounded_window_around_creation(self):
        from datetime import datetime, timezone
        client, store = Mock(), Mock()
        client.incidents.return_value = []
        client.events.return_value = []
        store.active.return_value = True
        store.seen.return_value = True
        store.needs_event_refresh.return_value = True
        store.stored_incident.return_value = {'id': 'old', 'created': T}
        self.m.collect(self.config, client, store, now=datetime(2026, 10, 21, tzinfo=timezone.utc),
                       extra_incidents=['old'])
        _, start, end = client.events.call_args.args
        self.assertGreater(start.timestamp(), 0)
        self.assertLessEqual((end - start).total_seconds(), 2 * 72 * 3600)
        self.assertEqual(start.year, 2019)
        self.assertEqual(end.year, 2020)

    def test_http_400_records_request_context_and_redacts_server_excerpt(self):
        from datetime import datetime, timezone
        session = Mock()
        session.request.return_value = base_tests.streaming_response(
            400, b'Unknown field; Authorization: Bearer secret another=pat_EXAMPLE_NOT_A_REAL_TOKEN')
        client = self.m.Client(self.config, session)
        with self.assertRaises(self.m.SIEMError) as caught:
            client.events(A, datetime.fromtimestamp(1792486213, timezone.utc),
                          datetime.fromtimestamp(1792486218, timezone.utc))
        details = caught.exception.diagnostic
        self.assertEqual(details['endpoint'], '/api/events/v3/events/')
        self.assertEqual(details['method'], 'POST')
        self.assertEqual(details['request_revision'], self.m.REQUEST_REVISION)
        self.assertEqual(details['time_from'], 1792486213)
        self.assertEqual(details['time_to'], 1792486218)
        self.assertIn('Unknown field', details['response_excerpt'])
        self.assertNotIn('secret', str(details))
        self.assertNotIn('pat_EXAMPLE_NOT_A_REAL_TOKEN', str(details))
        self.assertNotIn('headers', details)
        self.assertLessEqual(len(details['response_excerpt']), 1024)

    def test_event_failure_diagnostic_is_saved_in_alert_source(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'incident'}]
        client.events.side_effect = self.m.SIEMError('HTTP 400', code='http_400',
            diagnostic={'endpoint': '/api/events/v3/events/', 'response_excerpt': 'Unknown field'})
        store.active.return_value = True
        store.seen.return_value = False
        self.m.collect(self.config, client, store)
        errors = store.create.call_args.args[1]['alert_source_content']['event_collection']['errors']
        self.assertEqual(errors[0]['reason'], 'http_400')
        self.assertEqual(errors[0]['endpoint'], '/api/events/v3/events/')
        self.assertEqual(errors[0]['response_excerpt'], 'Unknown field')


if __name__ == '__main__':
    unittest.main()
