"""Read streamed MaxPatrol responses with a cap on decoded body bytes."""
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from requests import Response


class ResponseLimitError(ValueError):
    """The decoded response exceeded the limit; no body is exposed."""

    def __init__(self, bytes_read: int):
        self.bytes_read = bytes_read
        super().__init__(f'MaxPatrol response exceeded the byte limit ({bytes_read} bytes read)')


def read_response_bytes(response: 'Response', max_bytes: int) -> bytes:
    """Consume a stream=True response, limiting decompressed bytes, and close it."""
    body = bytearray()
    bytes_read = 0
    try:
        for chunk in response.iter_content(chunk_size=65536):
            bytes_read += len(chunk)
            if bytes_read > max_bytes:
                raise ResponseLimitError(bytes_read)
            body.extend(chunk)
        return bytes(body)
    finally:
        response.close()


def read_json_response(response: 'Response', max_bytes: int) -> tuple[dict, int]:
    """Parse a bounded JSON object; let malformed/oversized responses fail."""
    body = read_response_bytes(response, max_bytes)
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError('MaxPatrol JSON response must be an object')
    return payload, len(body)
