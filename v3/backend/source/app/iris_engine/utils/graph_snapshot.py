"""Validate data URLs for captured investigation graphs."""

import base64
import binascii


def png_snapshot_base64(value):
    prefix = 'data:image/png;base64,'
    if not isinstance(value, str) or len(value) > 1_500_000 or not value.startswith(prefix):
        return None
    payload = value[len(prefix):]
    try:
        png = base64.b64decode(payload, validate=True)
    except binascii.Error:
        return None
    if (len(png) < 33 or png[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
            or not all(0 < int.from_bytes(png[start:start + 4], 'big') <= 4096 for start in (16, 20))):
        return None
    return payload
