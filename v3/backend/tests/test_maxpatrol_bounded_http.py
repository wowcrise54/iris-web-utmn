"""Bound decoded MaxPatrol responses before JSON parsing or error reporting."""
import importlib.util
import json
from pathlib import Path
import tracemalloc
import unittest


MODULE_PATH = (Path(__file__).resolve().parents[1] / 'source' /
               'iris_maxpatrol_module' / 'bounded_http.py')


class StreamResponse:
    """Model requests' iter_content interface, which yields decoded bytes."""

    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False
        self.chunks_read = 0

    def iter_content(self, chunk_size):
        if chunk_size != 65536:
            raise AssertionError('Stream reads must use bounded chunks')
        for chunk in self.chunks:
            self.chunks_read += 1
            yield chunk

    def close(self):
        self.closed = True


class BoundedHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('maxpatrol_bounded_http', MODULE_PATH)
        cls.transport = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.transport)

    def test_small_object_at_exact_limit_preserves_message_and_byte_count(self):
        response = StreamResponse([b'', b'{"message":', b'"ok"}'])
        self.assertEqual(self.transport.read_json_response(response, 16),
                         ({'message': 'ok'}, 16))
        self.assertTrue(response.closed)

    def test_split_utf8_is_decoded_after_all_bounded_chunks_arrive(self):
        response = StreamResponse([b'{"message":"\xd0', b'\xb4\xd0', b'\xb0"}'])
        self.assertEqual(self.transport.read_json_response(response, 18),
                         ({'message': '\u0434\u0430'}, 18))
        self.assertTrue(response.closed)

    def test_decoded_response_over_limit_closes_without_reading_rest(self):
        # Content-Length/compressed wire size must not determine this limit.
        response = StreamResponse([b'a' * 5, b'b' * 6, b'never consumed'])
        response.headers = {'Content-Length': '1', 'Content-Encoding': 'gzip'}
        with self.assertRaises(self.transport.ResponseLimitError) as caught:
            self.transport.read_response_bytes(response, 10)
        self.assertEqual(caught.exception.bytes_read, 11)
        self.assertNotIn('bbbbb', str(caught.exception))
        self.assertEqual(response.chunks_read, 2)
        self.assertTrue(response.closed)

    def test_oversized_single_event_raises_instead_of_returning_partial_json(self):
        response = StreamResponse([b'{"events":[{"id":1,"data":"', b'x' * 40,
                                   b'"}]}'])
        with self.assertRaises(self.transport.ResponseLimitError):
            self.transport.read_json_response(response, 32)
        self.assertEqual(response.chunks_read, 2)
        self.assertTrue(response.closed)

    def test_malformed_json_closes_response(self):
        response = StreamResponse([b'{bad json'])
        with self.assertRaises(json.JSONDecodeError):
            self.transport.read_json_response(response, 100)
        self.assertTrue(response.closed)

    def test_nonobject_json_is_rejected(self):
        for payload in (b'[]', b'null', b'1', b'"message"'):
            with self.subTest(payload=payload):
                response = StreamResponse([payload])
                with self.assertRaises(ValueError):
                    self.transport.read_json_response(response, 100)
                self.assertTrue(response.closed)

    def test_stream_failure_closes_response(self):
        def chunks():
            yield b'{'
            raise OSError('connection interrupted')

        response = StreamResponse(chunks())
        with self.assertRaises(OSError):
            self.transport.read_response_bytes(response, 100)
        self.assertTrue(response.closed)

    def test_lazy_large_response_memory_scales_with_cap(self):
        cap = 1024 * 1024
        response = StreamResponse(b'x' * 65536 for _ in range(16384))
        tracemalloc.start()
        try:
            with self.assertRaises(self.transport.ResponseLimitError):
                self.transport.read_response_bytes(response, cap)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 8 * cap)
        self.assertEqual(response.chunks_read, 17)
        self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
