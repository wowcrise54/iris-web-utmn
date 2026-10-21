"""Execute the SIEM read route with inert HTTP/auth/database boundaries."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROUTE = Path(__file__).parents[1] / 'v3/backend/source/app/blueprints/rest/v2/alerts_routes/siem_events.py'


class NotFound(Exception):
    pass


class ProcessingError(Exception):
    def get_message(self):
        return 'Access denied'

    def get_data(self):
        return None


class SiemEventsRouteTests(unittest.TestCase):
    def route(self, *, args=None, denied=False, missing=False, permission=True):
        self.reads = []
        self.authorized = SimpleNamespace(alert_id=42)
        def authorize(user, permissions, identifier, **kwargs):
            self.assertEqual(identifier, 42)
            self.assertEqual(user.id, 7)
            self.assertIs(kwargs['fallback_customer_access'], customer_access)
            if missing:
                raise NotFound()
            if denied:
                raise ProcessingError()
            return self.authorized
        def read(alert, **kwargs):
            self.assertIs(alert, self.authorized)
            self.reads.append(kwargs)
            return {'data': [{'event_key': 'one', 'event': {'message': 'full event'}}],
                    'next_offset': 1, 'has_more': True, 'total': 8, 'offset': kwargs['offset'], 'limit': kwargs['limit']}
        def customer_access(customer):
            return False
        def requires(value):
            self.assertEqual(value, 'alerts_read')
            def decorate(function):
                return lambda *a, **kw: function(*a, **kw) if permission else ('denied', 403)
            return decorate
        class Blueprint:
            def __init__(self, *a, **kw):
                pass
            def get(self, path):
                return lambda function: function
        env = dict(Blueprint=Blueprint, request=SimpleNamespace(args=args or {}),
                   session={'permissions': 13}, iris_current_user=SimpleNamespace(id=7),
                   alerts_get=authorize, list_alert_events=read,
                   ac_current_user_has_customer_access=customer_access, ac_api_requires=requires,
                   Permissions=SimpleNamespace(alerts_read='alerts_read'),
                   ObjectNotFoundError=NotFound, BusinessProcessingError=ProcessingError,
                   response_api_success=lambda data: (data, 200),
                   response_api_not_found=lambda: ('missing', 404),
                   response_api_error=lambda message, **kw: (message, 400))
        self.assertTrue(ROUTE.exists(), 'SIEM event read route is missing')
        tree = ast.parse(ROUTE.read_text(encoding='utf-8'))
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        exec(compile(tree, str(ROUTE), 'exec'), env)
        return env['get_siem_events'](42)

    def test_returns_events_from_authorized_alert_using_requested_offset(self):
        payload, status = self.route(args={'offset': '3', 'limit': '10'})
        self.assertEqual(status, 200)
        self.assertEqual(payload['data'][0]['event']['message'], 'full event')
        self.assertEqual(self.reads, [{'offset': 3, 'limit': 10}])

    def test_caps_page_size(self):
        self.route(args={'limit': '1000000'})
        self.assertEqual(self.reads, [{'offset': 0, 'limit': 25}])

    def test_invalid_offsets_and_limits_do_not_read(self):
        for args in ({'offset': '-1'}, {'limit': '0'}, {'offset': 'oops'}, {'limit': '-1'}):
            with self.subTest(args=args):
                self.assertEqual(self.route(args=args)[1], 400)
                self.assertEqual(self.reads, [])

    def test_customer_acl_and_missing_alert_do_not_read_events(self):
        for options, status in (({'denied': True}, 400), ({'missing': True}, 404), ({'permission': False}, 403)):
            with self.subTest(options=options):
                self.assertEqual(self.route(**options)[1], status)
                self.assertEqual(self.reads, [])


if __name__ == '__main__':
    unittest.main()
