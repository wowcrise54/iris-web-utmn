"""Nested event traversal using inert MP10 28.0 responses."""
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
    def setUp(self):
        self.m = base_tests.MaxPatrolTests().core()
        self.config = self.m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'secret'})
        self.client = self.m.Client(self.config)

    def test_full_event_unwraps_28_data_and_preserves_all_fields(self):
        full = event(A, [B], body='original', custom={'nested': [False, None, 0]})
        self.client.request = Mock(return_value={'event': {'Data': [full], 'TotalCount': 1}})
        self.assertEqual(self.client.event_details(A, T), full)
        call = self.client.request.call_args
        self.assertEqual(call.args, ('GET', f'/api/events/v2/events/{A}/normalized'))
        self.assertEqual(call.kwargs['params'], {'time': T})

    def test_subevent_endpoint_paginates_without_incident_time_window(self):
        self.client.request = Mock(side_effect=[{'events': [event(B)] * 250, 'token': 'page-token'},
                                               {'events': [event(C)]}])
        self.assertEqual(len(self.client.subevents(A, T)), 251)
        first, second = self.client.request.call_args_list
        self.assertEqual(first.args, ('POST', f'/api/events/v2/subevents/{A}'))
        self.assertEqual(first.kwargs['params']['field'], 'subevents')
        self.assertEqual(first.kwargs['body']['timeFrom'], 0)
        self.assertEqual(second.kwargs['params']['offset'], 250)
        self.assertEqual(second.kwargs['params']['token'], 'page-token')
        self.assertNotIn('incidentId', first.kwargs['params'])

    def test_nested_shared_children_cycles_and_same_normalizer_are_preserved(self):
        client = Mock()
        nodes = {A: event(A, [B, C]), B: event(B, [C]), C: event(C, [A], body='raw child')}
        client.event_details.side_effect = lambda uid, _time: nodes[uid]
        client.subevents.side_effect = lambda uid, _time, **_options: [nodes[child] for child in nodes[uid]['subevents']]
        result = self.m.expand_subevents(client, [event(A)])
        self.assertEqual({row['uuid'] for row in result['events']}, {A, B, C})
        self.assertEqual(client.event_details.call_count, 3)
        self.assertEqual(client.subevents.call_count, 3)
        self.assertTrue(result['event_collection']['complete'])
        tree = result['event_tree'][0]
        self.assertEqual(tree['uuid'], A)
        self.assertEqual(tree['subevents'][0]['uuid'], B)
        self.assertTrue(tree['subevents'][0]['subevents'][0]['subevents'][0]['reference'])

    def test_missing_events_are_explicit_and_successful_children_survive(self):
        client = Mock()
        client.event_details.side_effect = [event(A, [B, C]), event(B, body='retained')]
        client.subevents.return_value = [event(B)]
        result = self.m.expand_subevents(client, [event(A)])
        self.assertFalse(result['event_collection']['complete'])
        self.assertIn(C, result['event_collection']['missing_uuids'])
        self.assertEqual(len(result['events']), 2)

    def test_detail_error_keeps_root_and_does_not_expose_exception_text(self):
        client = Mock()
        client.event_details.side_effect = self.m.SIEMError('secret response', code='http_403')
        with self.assertLogs(self.m.log, level='INFO') as captured:
            result = self.m.expand_subevents(client, [event(A)])
        self.assertEqual(result['events'][0]['uuid'], A)
        self.assertFalse(result['event_collection']['complete'])
        self.assertIn('http_403', str(result['event_collection']))
        self.assertNotIn('secret response', str(result))
        self.assertNotIn('secret response', '\n'.join(captured.output))

    def test_traversal_limit_is_reported_not_silent(self):
        client = Mock()
        client.event_details.return_value = event(A, [B, C])
        client.subevents.return_value = [event(B), event(C)]
        result = self.m.expand_subevents(client, [event(A)], max_events=1)
        self.assertFalse(result['event_collection']['complete'])
        self.assertEqual(result['event_collection']['limit_reached'], True)

    def test_empty_normalized_wrapper_is_not_a_complete_event(self):
        self.client.request = Mock(return_value={'event': {'Data': [], 'TotalCount': 0}})
        with self.assertRaises(self.m.SIEMError):
            self.client.event_details(A, T)

    def test_uuid_from_meta_supported_and_mismatched_response_rejected(self):
        self.client.request = Mock(return_value={'event': event(B)})
        with self.assertRaises(self.m.SIEMError):
            self.client.event_details(A, T)
        client = Mock()
        client.event_details.return_value = event(A)
        result = self.m.expand_subevents(client, [{'_meta': {'id': A, 'time': T}}])
        self.assertTrue(result['event_collection']['complete'])

    def test_collect_saves_expanded_materials_and_refreshes_existing_alert(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'incident'}]
        client.detail.return_value = {'name': 'Incident'}
        client.events.return_value = [event(A, [B])]
        client.event_details.side_effect = [event(B, body='raw child')]
        client.subevents.return_value = [event(B)]
        store.active.return_value = True
        store.seen.return_value = True
        store.needs_event_refresh.return_value = True
        self.assertEqual(self.m.collect(self.config, client, store), 0)
        store.create.assert_not_called()
        content = store.refresh_events.call_args.args[1]
        self.assertEqual({row['uuid'] for row in content['events']}, {A, B})
        self.assertTrue(content['event_collection']['complete'])

    def test_malformed_child_ids_do_not_claim_complete(self):
        client = Mock()
        client.event_details.return_value = event(A, ['not-a-uuid'])
        client.subevents.return_value = []
        self.assertFalse(self.m.expand_subevents(client, [event(A)])['event_collection']['complete'])

    def test_refresh_outside_incident_discovery_window(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = []
        client.detail.return_value = {'name': 'Old incident'}
        client.events.return_value = []
        store.active.return_value = True
        store.seen.return_value = True
        store.needs_event_refresh.return_value = True
        self.m.collect(self.config, client, store, extra_incidents=['old', 'old'])
        store.refresh_events.assert_called_once()

    def test_child_pagination_stops_at_budget_and_keeps_partial_rows(self):
        self.client.request = Mock(return_value={'events': [event(B), event(C)]})
        rows = self.client.subevents(A, T, max_events=2)
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows.complete)
        self.assertEqual(rows.reason, 'event_limit')
        self.assertEqual(self.client.request.call_count, 1)

    def test_child_pagination_checks_disable_before_next_page(self):
        self.client.request = Mock(return_value={'events': [event(B)] * 250})
        rows = self.client.subevents(A, T, is_active=Mock(side_effect=[True, False]))
        self.assertEqual(len(rows), 250)
        self.assertFalse(rows.complete)
        self.assertEqual(rows.reason, 'module_inactive')
        self.assertEqual(self.client.request.call_count, 1)

    def test_later_page_failure_retains_first_page(self):
        self.client.request = Mock(side_effect=[{'events': [event(B)] * 250},
                                               self.m.SIEMError('secret', code='timeout')])
        rows = self.client.subevents(A, T)
        self.assertEqual(len(rows), 250)
        self.assertFalse(rows.complete)
        self.assertEqual(rows.reason, 'timeout')

    def test_client_contract_to_alert_keeps_old_child_raw_and_normalized_fields(self):
        self.client.incidents = Mock(return_value=[{'id': 'incident'}])
        self.client.detail = Mock(return_value={'name': 'Incident'})
        self.client.request = Mock(return_value={'errors': None, 'events': [
            event(B, body='<Event>original</Event>', mime='text/xml',
                  custom={'process': {'name': 'example'}}), event(A, [B])], 'token': 'page-token'})
        store = Mock()
        store.active.return_value = True
        store.seen.return_value = False
        self.assertEqual(self.m.collect(self.config, self.client, store), 1)
        content = store.create.call_args.args[1]['alert_source_content']
        self.assertEqual(len(content['events']), 2)
        child = content['event_tree'][0]['subevents'][0]['event']
        self.assertEqual(child['body'], '<Event>original</Event>')
        self.assertEqual(child['custom']['process']['name'], 'example')
        self.assertTrue(content['event_collection']['complete'])
        self.assertEqual(self.client.request.call_args_list[0].kwargs['body']['timeFrom'], 0)
        self.assertEqual(self.client.request.call_count, 1)

    def test_v3_full_response_builds_tree_without_detail_or_subevent_requests(self):
        rows = [event(B, body='{"Event":{"Data":[]}}', **{'count.subevents': None,
            '_checkpoint': 123, '_presentation': [], '_whitelisting': None}),
            event(A, [B], **{'count.subevents': None})]
        client = Mock()
        result = self.m.expand_subevents(client, rows, source_complete=True)
        client.event_details.assert_not_called()
        client.subevents.assert_not_called()
        self.assertTrue(result['event_collection']['complete'])
        self.assertEqual(len(result['event_tree']), 1)
        self.assertEqual(result['event_tree'][0]['uuid'], A)
        child = result['event_tree'][0]['subevents'][0]['event']
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


if __name__ == '__main__':
    unittest.main()
