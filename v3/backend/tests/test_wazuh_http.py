"""Exercise the actual HTTPS client against a local Indexer-shaped server."""
import base64
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import sys
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from iris_wazuh_module.collector import Client, collect_window


@pytest.fixture
def indexer(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    requests_seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args): pass
        def do_POST(self):
            if self.headers.get('Authorization') != 'Basic ' + base64.b64encode(b'reader:secret').decode():
                self.send_response(401); self.end_headers(); return
            length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(length))
            requests_seen.append((self.path, body))
            if '/_search?' in self.path:
                hits = [{'_id': '1'}, {'_id': '2'}]
            else:
                hits = [{'_id': '3'}] if body['scroll_id'] == 'one' else []
            scroll = 'one' if '/_search?' in self.path else ('two' if hits else 'three')
            payload = json.dumps({'_scroll_id': scroll, 'timed_out': False, '_shards': {'failed': 0},
                                  'hits': {'hits': hits}}).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        def do_DELETE(self):
            length = int(self.headers['Content-Length'])
            requests_seen.append((self.path, json.loads(self.rfile.read(length))))
            self.send_response(200); self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'https://localhost:{server.server_port}', str(cert_path), requests_seen
    finally:
        server.shutdown(); thread.join(); server.server_close()


def test_real_https_basic_scroll_and_cleanup(indexer):
    url, cert, seen = indexer
    client = Client(url, 'reader', 'secret', 'wazuh-alerts-4.x-*', verify=cert)
    try:
        assert [item['_id'] for item in client.hits('start', 'end', 12)] == ['1', '2', '3']
        assert seen[0][1]['query']['bool']['filter'][0] == {'range': {'rule.level': {'gte': 12}}}
        assert seen[-1] == ('/_search/scroll', {'scroll_id': ['three']})
    finally:
        client.close()


def test_real_https_auth_and_tls_errors_leave_watermark(indexer):
    url, cert, _seen = indexer
    class Store:
        watermark = 0
        def seen(self, _hit): return False
        def create(self, _hit): raise AssertionError('unexpected result')
        def advance(self, value): self.watermark = value
    for password, verify, error in [('wrong', cert, requests.HTTPError),
                                    ('secret', True, requests.exceptions.SSLError)]:
        store = Store()
        client = Client(url, 'reader', password, 'wazuh-alerts-4.x-*', verify=verify)
        try:
            with pytest.raises(error):
                collect_window(client.hits('start', 'end', 12), store, 1)
            assert store.watermark == 0
        finally:
            client.close()
