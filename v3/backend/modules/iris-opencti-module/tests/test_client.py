import json
import threading
import unittest
import time
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from iris_opencti_module.client import OpenCTIClient, OpenCTIError, normalize_ioc


def graphql_response(**connections):
    return {**{key: {'edges': [], 'pageInfo': {'hasNextPage': False}}
               for key in ('stixCyberObservables', 'indicators', 'stixCoreRelationships')}, **connections}


class ClientTests(unittest.TestCase):
    def test_typed_normalization(self):
        self.assertEqual(normalize_ioc('ip-src', '2001:0db8::1'), ('IPv6-Addr', '2001:db8::1', 'value'))
        self.assertEqual(normalize_ioc('domain', 'ExAmPlE.org.'), ('Domain-Name', 'example.org', 'value'))
        self.assertEqual(normalize_ioc('sha256', 'A' * 64), ('StixFile', 'a' * 64, 'hashes.SHA-256'))
        self.assertEqual(normalize_ioc('url', 'https://example.org/Path?A=B')[1], 'https://example.org/Path?A=B')

    def test_invalid_and_composite_types_are_not_guessed(self):
        for kind, value in [('ip-dst', 'not an ip'), ('md5', 'abc'), ('domain|ip', 'example.org|1.2.3.4'), ('url', 'javascript:alert(1)')]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                normalize_ioc(kind, value)

    def test_exact_typed_matching_and_indicator_lifecycle(self):
        client = OpenCTIClient('https://cti.example', 'secret')
        client.query = lambda *args: graphql_response(stixCyberObservables={'edges': [
            {'node': {'id': 'one', 'entity_type': 'Domain-Name', 'observable_value': 'EXAMPLE.ORG',
                      'indicators': {'edges': [
                          {'node': {'id': 'active', 'name': 'Active', 'revoked': False}},
                          {'node': {'id': 'revoked', 'revoked': True}},
                          {'node': {'id': 'expired', 'valid_until': '2000-01-01T00:00:00Z'}},
                          {'node': {'id': 'future', 'valid_from': '2999-01-01T00:00:00Z'}}
                      ], 'pageInfo': {'hasNextPage': False}}}},
            {'node': {'id': 'partial', 'entity_type': 'Domain-Name', 'observable_value': 'sub.example.org'}},
            {'node': {'id': 'wrong-type', 'entity_type': 'Url', 'observable_value': 'example.org'}}
        ], 'pageInfo': {'hasNextPage': False}})
        result = client.lookup('domain', 'example.org')
        self.assertEqual(result['status'], 'matched')
        self.assertEqual([x['id'] for x in result['observables']], ['one'])
        self.assertEqual([x['validity'] for x in result['indicators']], ['active', 'revoked', 'expired', 'not_yet_valid'])
        self.assertIn('/dashboard/observations/indicators/active', result['indicators'][0]['url'])

    def test_hash_is_verified_against_hash_algorithm_not_file_name(self):
        client = OpenCTIClient('https://cti.example', 'secret')
        client.query = lambda *args: graphql_response(stixCyberObservables={'edges': [
            {'node': {'id': 'wrong', 'entity_type': 'StixFile', 'observable_value': 'a' * 32, 'hashes': []}},
            {'node': {'id': 'right', 'entity_type': 'StixFile', 'hashes': [{'algorithm': 'MD5', 'hash': 'A' * 32}]}}
        ], 'pageInfo': {'hasNextPage': False}})
        self.assertEqual([o['id'] for o in client.lookup('md5', 'a' * 32)['observables']], ['right'])

    def test_empty_result_is_not_error(self):
        client = OpenCTIClient('https://cti.example', 'secret')
        client.query = lambda *args: graphql_response()
        self.assertEqual(client.lookup('domain', 'example.org')['status'], 'no_match')

    def test_pagination_and_exact_filter_variables(self):
        calls = []
        client = OpenCTIClient('https://cti.example', 'secret')
        def query(document, variables):
            if 'IrisOpenCTIIndicators' in document:
                return graphql_response()
            calls.append(variables)
            return graphql_response(stixCyberObservables={'edges': [], 'pageInfo': {'hasNextPage': len(calls) == 1, 'endCursor': 'next'}})
        client.query = query
        client.lookup('domain', 'example.org')
        self.assertEqual(calls[0]['types'], ['Domain-Name'])
        self.assertEqual(calls[0]['filters']['filters'][0]['operator'], 'eq')
        self.assertEqual(calls[1]['after'], 'next')

    def test_bad_connection_settings(self):
        for url in ['file:///etc/passwd', 'https://user:pass@cti.example', 'https://cti.example/?token=x', '']:
            with self.subTest(url=url), self.assertRaises(OpenCTIError):
                OpenCTIClient(url, 'secret')

    def test_indicator_without_observable_is_found_only_by_exact_stix_pattern(self):
        client = OpenCTIClient('https://cti.example', 'secret')
        pattern = "[domain-name:value = 'example.org']"
        client.query = lambda *args: graphql_response(indicators={'edges': [
            {'node': {'id': 'one', 'pattern': pattern, 'pattern_type': 'stix'}},
            {'node': {'id': 'wrong', 'pattern': "[url:value = 'example.org']", 'pattern_type': 'stix'}}
        ]})
        result = client.lookup('domain', 'example.org')
        self.assertEqual([x['id'] for x in result['indicators']], ['one'])
        self.assertEqual(result['observables'], [])

    def test_truncated_linked_indicators_are_explicitly_partial(self):
        client = OpenCTIClient('https://cti.example', 'secret')
        client.query = lambda *args: graphql_response(stixCyberObservables={'edges': [{'node': {
            'id': 'one', 'entity_type': 'Domain-Name', 'observable_value': 'example.org',
            'indicators': {'edges': [], 'pageInfo': {'hasNextPage': True}}
        }}]})
        self.assertEqual(client.lookup('domain', 'example.org')['status'], 'partial')

    def test_pagination_limit_is_not_reported_as_no_match(self):
        client = OpenCTIClient('https://cti.example', 'secret')
        page = [0]
        def query(*args):
            page[0] += 1
            return graphql_response(stixCyberObservables={'edges': [], 'pageInfo': {'hasNextPage': True, 'endCursor': str(page[0])}})
        client.query = query
        with self.assertRaises(OpenCTIError) as raised:
            client.lookup('domain', 'example.org')
        self.assertEqual(raised.exception.status, 'result_limit')


class HTTPContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                cls.requests.append((self.path, self.headers.get('Authorization'), body))
                if body['query'] == 'slow':
                    time.sleep(0.05)
                if body['query'] == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', '/redirect-target')
                    payload = {}
                elif body['query'] == 'unavailable':
                    self.send_response(503)
                    payload = {}
                elif body['query'] == 'unauthorized':
                    self.send_response(401)
                    payload = {'secret': 'sensitive-server-body'}
                else:
                    self.send_response(200)
                    payload = {'errors': [{'message': 'sensitive-server-body'}]} if body['query'] == 'bad-schema' else {'data': {'about': {'version': 'fixture'}}}
                    if body['query'] == 'gql-denied':
                        payload = {'errors': [{'message': 'sensitive-server-body', 'extensions': {'code': 'FORBIDDEN'}}]}
                self.end_headers()
                try:
                    self.wfile.write(json.dumps(payload).encode())
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_real_http_post_bearer_and_graphql_path(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}/cti', 'secret')
        self.assertEqual(client.query('check', {})['about']['version'], 'fixture')
        self.assertEqual(self.requests[-1][:2], ('/cti/graphql', 'Bearer secret'))

    def test_sanitized_errors(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret')
        for document, expected in [('unauthorized', 'unauthorized'), ('gql-denied', 'unauthorized'),
                                   ('bad-schema', 'schema_error'), ('unavailable', 'unavailable')]:
            with self.assertRaises(OpenCTIError) as raised:
                client.query(document, {})
            self.assertEqual(raised.exception.status, expected)
            self.assertNotIn('sensitive', str(raised.exception))
            self.assertNotIn('secret', str(raised.exception))

    def test_request_logs_do_not_include_credentials_variables_or_response_body(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret')
        with self.assertLogs('iris_opencti_module', level='DEBUG') as captured:
            client.query('check', {'value': 'private.example'})
            with self.assertRaises(OpenCTIError):
                client.query('unauthorized', {'value': 'private.example'})
        output = '\n'.join(captured.output)
        for expected in ('request_started', 'request_completed', 'request_failed', 'status=unauthorized', 'duration_ms='):
            self.assertIn(expected, output)
        for private in ('secret', 'private.example', 'sensitive-server-body', '127.0.0.1'):
            self.assertNotIn(private, output)

    def test_trace_never_logs_bodies_and_correlates_http_errors(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret')
        with patch.dict('os.environ', {'IRIS_OPENCTI_LOG_LEVEL': 'TRACE'}), self.assertLogs('iris_opencti_module', level='DEBUG') as captured:
            client.query('check', {'value': 'private.example', 'echo': 'secret'})
            with self.assertRaises(OpenCTIError):
                client.query('unauthorized', {})
        output = '\n'.join(captured.output)
        self.assertNotIn('private.example', output)
        self.assertNotIn('sensitive-server-body', output)
        self.assertIn('http_status=401', output)
        self.assertIn('bytes=', output)
        self.assertNotIn('secret', output)
        self.assertNotIn('Bearer', output)
        requests = [r for r in captured.records if 'TRACE request ' in r.getMessage()]
        responses = [r for r in captured.records if 'TRACE response ' in r.getMessage()]
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(responses), 2)
        for request, response in zip(requests, responses):
            self.assertEqual(request.getMessage().split('request_id=')[1].split()[0],
                             response.getMessage().split('request_id=')[1].split()[0])

    def test_trace_truncates_payload_and_is_off_in_debug(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret')
        with patch.dict('os.environ', {'IRIS_OPENCTI_LOG_LEVEL': 'TRACE'}), self.assertLogs('iris_opencti_module', level='DEBUG') as captured:
            client.query('check', {'value': 'x' * 20000 + 'secret'})
        self.assertIn('bytes=', '\n'.join(captured.output))
        self.assertNotIn('x' * 100, '\n'.join(captured.output))
        self.assertNotIn('secret', '\n'.join(captured.output))
        with patch.dict('os.environ', {'IRIS_OPENCTI_LOG_LEVEL': 'DEBUG', 'IRIS_OPENCTI_LOG_PAYLOADS': 'false'}), self.assertLogs('iris_opencti_module', level='DEBUG') as captured:
            client.query('check', {'value': 'private.example'})
        self.assertNotIn('TRACE', '\n'.join(captured.output))

    def test_timeout_is_exposed_as_a_safe_status(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret', timeout=0.005)
        with self.assertRaises(OpenCTIError) as raised:
            client.query('slow', {})
        self.assertEqual(raised.exception.status, 'timeout')

    def test_redirect_is_not_followed_with_the_bearer_token(self):
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret')
        with self.assertRaises(OpenCTIError) as raised:
            client.query('redirect', {})
        self.assertEqual(raised.exception.status, 'http_error')

    def test_disabled_guard_stops_transport_between_requests(self):
        enabled = [True]
        client = OpenCTIClient(f'http://127.0.0.1:{self.server.server_port}', 'secret', is_active=lambda: enabled[0])
        client.query('check', {})
        request_count = len(self.requests)
        enabled[0] = False
        with self.assertRaises(OpenCTIError) as raised:
            client.query('check', {})
        self.assertEqual(raised.exception.status, 'disabled')
        self.assertEqual(len(self.requests), request_count)


if __name__ == '__main__':
    unittest.main()
