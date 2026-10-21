"""Logging behaviour in a synchronous worker, without network calls."""
import warnings
from unittest.mock import Mock
import unittest

from urllib3.exceptions import InsecureRequestWarning
import test_maxpatrol as base_tests


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.m = base_tests.MaxPatrolTests().core()

    def client(self, *, verify_tls=True):
        config = self.m.Config.from_values({'siem_url': 'https://siem.local', 'api_token': 'test-secret',
                                           'verify_tls': verify_tls})
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {'ok': True}
        session.request.return_value = response
        return self.m.Client(config, session), session, response

    def test_configured_insecure_tls_has_one_notice_and_no_repeated_library_warning(self):
        client, session, response = self.client(verify_tls=False)

        def emit_warning(*_args, **_kwargs):
            warnings.warn_explicit("Unverified HTTPS request is being made to host 'siem.local'. Adding certificate verification is strongly advised.",
                InsecureRequestWarning, 'connectionpool.py', 1061, module='urllib3.connectionpool')
            return response

        session.request.side_effect = emit_warning
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            before = list(warnings.filters)
            with self.assertLogs(self.m.log, level='INFO') as output:
                client.detail('one')
                client.detail('two')
            self.assertEqual(warnings.filters, before)
        self.assertEqual(captured, [])
        text = '\n'.join(output.output)
        self.assertEqual(text.count('TLS certificate verification disabled'), 1)
        self.assertEqual(text.count('MaxPatrol HTTP completed:'), 2)
        self.assertFalse(session.request.call_args.kwargs['verify'])

    def test_other_tls_warnings_remain_visible(self):
        client, session, response = self.client(verify_tls=False)

        def emit_warning(*_args, **_kwargs):
            warnings.warn_explicit("Unverified HTTPS request is being made to host 'other.local'.",
                InsecureRequestWarning, 'connectionpool.py', 1061, module='urllib3.connectionpool')
            return response

        session.request.side_effect = emit_warning
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            client.detail('one')
        self.assertEqual(len(captured), 1)
        self.assertIn('other.local', str(captured[0].message))

    def test_context_is_carried_into_http_error_and_reset_after_scope(self):
        client, _, response = self.client()
        response.status_code = 400
        response.text = 'Invalid field. Bearer test-secret pat_NOT_A_REAL_CREDENTIAL'
        with self.assertLogs(self.m.log, level='INFO') as output:
            with self.m.logging_context(module=7, poll='poll-one', incident='incident-one'):
                with self.assertRaises(self.m.SIEMError):
                    client.detail('one')
            self.m.log.info('outside scope')
        text = '\n'.join(output.output)
        self.assertIn('module=7', text)
        self.assertIn('poll="poll-one"', text)
        self.assertIn('incident="incident-one"', text)
        self.assertIn('duration_ms=', text)
        self.assertIn('status=400', text)
        self.assertIn('Invalid field.', text)
        self.assertNotIn('test-secret', text)
        self.assertNotIn('pat_NOT_A_REAL_CREDENTIAL', text)
        self.assertNotIn('poll-one', output.output[-1])

    def test_verified_tls_does_not_suppress_warnings_or_emit_insecure_notice(self):
        client, session, response = self.client()

        def emit_warning(*_args, **_kwargs):
            warnings.warn_explicit("Unverified HTTPS request is being made to host 'siem.local'.",
                InsecureRequestWarning, 'connectionpool.py', 1061, module='urllib3.connectionpool')
            return response

        session.request.side_effect = emit_warning
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            client.detail('one')
        self.assertEqual(len(captured), 1)
        self.assertTrue(session.request.call_args.kwargs['verify'])

    def test_parallel_log_contexts_are_isolated_and_percent_signs_are_safe(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)

        def write(incident):
            with self.m.logging_context(incident=incident):
                barrier.wait(timeout=5)
                self.m.log.info('MaxPatrol test: value=%s', 'ok')

        with self.assertLogs(self.m.log, level='INFO') as output, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write, incident) for incident in ('first%id', 'second')]
            for future in futures:
                future.result(timeout=10)
        self.assertEqual(len(output.output), 2)
        first = next(line for line in output.output if 'first%id' in line)
        second = next(line for line in output.output if 'second' in line)
        self.assertNotIn('second', first)
        self.assertNotIn('first%id', second)
        self.assertIn('value=ok', first)

    def test_context_resets_when_scope_raises(self):
        with self.assertRaises(RuntimeError), self.m.logging_context(incident='failed-scope'):
            raise RuntimeError('test')
        with self.assertLogs(self.m.log, level='INFO') as output:
            self.m.log.info('MaxPatrol outside scope')
        self.assertNotIn('failed-scope', output.output[0])


if __name__ == '__main__':
    unittest.main()
