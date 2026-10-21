"""Event retrieval must use only the user's captured v3 request."""
import unittest
from unittest.mock import Mock

import test_maxpatrol as base_tests

A = '00000006-050d-0642-f000-0000255d3663'
B = '00000006-050d-0642-f000-0000255d3664'
C = '00000006-050d-0642-f000-0000255d3665'


class V3OnlyTests(unittest.TestCase):
    def setUp(self):
        self.m = base_tests.MaxPatrolTests().core()

    def test_missing_child_never_triggers_other_event_routes(self):
        config = self.m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'test-token'})
        session = Mock()

        def respond(_method, url, **_kwargs):
            response = Mock()
            response.status_code = 200 if url.endswith('/api/events/v3/events/') else 404
            response.text = 'unsupported route'
            response.json.return_value = {'events': [{'uuid': A, 'time': '2026-10-21T08:00:00Z',
                'subevents': [B], 'body': 'original'}]}
            return response

        session.request.side_effect = respond
        client = self.m.Client(config, session)
        client.incidents = Mock(return_value=[{'id': 'incident'}])
        client.detail = Mock(return_value={'name': 'Incident'})
        store = Mock()
        store.active.return_value = True
        store.seen.return_value = False
        self.m.collect(config, client, store)
        self.assertEqual([call.args[1] for call in session.request.call_args_list],
                         ['https://siem.local/api/events/v3/events/'])
        content = store.create.call_args.args[1]['alert_source_content']
        self.assertEqual(content['event_collection']['missing_uuids'], [B])
        self.assertFalse(content['event_collection']['complete'])
        self.assertEqual(content['events'][0]['body'], 'original')

    def test_pure_tree_builder_handles_shared_children_cycles_and_missing_ids(self):
        self.assertTrue(callable(getattr(self.m, 'build_event_materials', None)), 'Pure v3 tree builder is missing')
        rows = [{'uuid': B, 'subevents': [C]}, {'uuid': C, 'subevents': [A]},
                {'uuid': A, 'subevents': [B, C]}]
        result = self.m.build_event_materials(rows)
        self.assertTrue(result['event_collection']['complete'])
        self.assertEqual(len(result['events']), 3)
        self.assertEqual(result['event_links'][A], [B, C])


if __name__ == '__main__':
    unittest.main()
