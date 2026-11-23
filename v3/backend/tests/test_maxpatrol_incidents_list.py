"""Use the two working requests supplied by the user, without a card GET."""
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

import test_maxpatrol as base_tests


class IncidentsListTests(unittest.TestCase):
    def setUp(self):
        self.m = base_tests.MaxPatrolTests().core()
        self.config = self.m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'test-token'})

    def test_list_request_matches_supplied_contract(self):
        client = self.m.Client(self.config)
        client.request = Mock(return_value={'incidents': []})
        start = datetime(2026, 10, 14, 19, tzinfo=timezone.utc)
        list(client.incidents(start, datetime(2026, 10, 21, tzinfo=timezone.utc)))
        call = client.request.call_args
        self.assertEqual(call.args, ('POST', '/api/v2/incidents/'))
        self.assertEqual(call.kwargs['body'], {
            'offset': 0, 'limit': 50, 'groups': {'filterType': 'no_filter'},
            'timeFrom': '2026-10-14T19:00:00.000Z', 'timeTo': None, 'filterTimeType': 'creation',
            'filter': {'select': ['key', 'name', 'category', 'type', 'status', 'created', 'assigned'],
                'where': 'status != "Closed"', 'orderby': [
                    {'field': 'created', 'sortOrder': 'descending'},
                    {'field': 'status', 'sortOrder': 'ascending'},
                    {'field': 'severity', 'sortOrder': 'descending'}]},
            'queryIds': ['all_incidents']})

    def test_import_uses_only_list_and_events_requests(self):
        session = Mock()
        row = {'id': 'incident-id', 'key': 'INC-1', 'name': 'From list', 'status': 'New',
               'created': '2026-10-21T08:00:00Z', 'description': 'Incident details\n\nAffected host: workstation'}

        def respond(method, url, **_kwargs):
            response = Mock(status_code=200)
            if (method, url) == ('POST', 'https://siem.local/api/v2/incidents/'):
                response.json.return_value = {'incidents': [row]}
            elif (method, url) == ('POST', 'https://siem.local/api/events/v3/events/'):
                response.json.return_value = {'events': []}
            else:
                self.fail(f'Unapproved request: {method} {url}')
            return response

        session.request.side_effect = respond
        client = self.m.Client(self.config, session)
        store = Mock()
        store.active.return_value = True
        store.seen.return_value = False
        self.assertEqual(self.m.collect(self.config, client, store), 1)
        self.assertEqual(session.request.call_count, 2)
        payload = store.create.call_args.args[1]
        self.assertEqual(payload['alert_title'], 'From list')
        self.assertEqual(payload['alert_description'], row['description'])
        self.assertEqual(payload['alert_source_content']['incident'], row)
        self.assertEqual(payload['alert_source_content']['incident_source'], 'incidents_list_v2')

    def test_missing_incident_description_has_no_placeholder(self):
        now = datetime.now(timezone.utc)
        for detail in ({}, {'description': '  '}, {'description': 'Incident Form MaxPatrol SIEM'}):
            with self.subTest(detail=detail):
                self.assertIsNone(self.m.alert_payload(self.config, 'one', detail, [], now)['alert_description'])

    def test_import_uses_incident_description_returned_in_events(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one'}]
        client.events.return_value = [{'incident.description': 'Description from event'}]
        store.active.return_value = True
        store.seen.return_value = False
        self.assertEqual(self.m.collect(self.config, client, store), 1)
        payload = store.create.call_args.args[1]
        self.assertEqual(payload['alert_description'], 'Description from event')

    def test_import_prefers_incident_correlation_text_over_other_events_and_description(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'one', 'description': 'Incident card description'}]
        client.events.return_value = [
            {'text': 'Raw child event text'},
            {'correlation_type': 'event', 'text': 'Other correlation text'},
            {'correlation_type': 'incident', 'text': '  '},
            {'correlation_type': 'incident', 'text': 'Incident correlation text'},
        ]
        store.active.return_value = True
        store.seen.return_value = False
        self.assertEqual(self.m.collect(self.config, client, store), 1)
        self.assertEqual(store.create.call_args.args[1]['alert_description'], 'Incident correlation text')

    def test_refresh_merges_list_fields_with_saved_extra_fields(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'existing', 'name': 'Updated name', 'status': 'New'}]
        client.events.return_value = []
        store.active.return_value = True
        store.seen.return_value = True
        store.needs_event_refresh.return_value = True
        store.stored_incident.return_value = {'id': 'existing', 'name': 'Old name', 'description': 'Saved extra data'}
        self.m.collect(self.config, client, store)
        materials = store.refresh_events.call_args.args[1]
        self.assertEqual(materials['incident']['name'], 'Updated name')
        self.assertEqual(materials['incident']['description'], 'Saved extra data')
        self.assertEqual(materials['incident_source'], 'incidents_list_v2')
        store.create.assert_not_called()

    def test_closed_incident_is_not_imported(self):
        client, store = Mock(), Mock()
        client.incidents.return_value = [{'id': 'closed', 'name': 'Closed incident', 'status': 'Closed'}]
        store.active.return_value = True
        store.seen.return_value = False
        self.assertEqual(self.m.collect(self.config, client, store), 0)
        client.events.assert_not_called()
        store.create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
