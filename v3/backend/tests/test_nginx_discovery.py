"""Opt-in Docker regression: nginx must follow service IP changes without reload.

Run with IRIS_NGINX_DOCKER_TEST=1. Uses existing images, an isolated network,
no published ports, no application containers, credentials or data volumes.
"""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid


@unittest.skipUnless(os.environ.get('IRIS_NGINX_DOCKER_TEST') == '1', 'opt-in Docker test')
class NginxDiscoveryTests(unittest.TestCase):
    def test_routes_follow_replaced_backend_and_frontend(self):
        prefix = 'iris-nginx-probe-' + uuid.uuid4().hex[:10]
        network, service, proxy = prefix + '-net', prefix + '-service', prefix + '-proxy'
        fixture = Path(__file__).resolve().parents[1] / 'docker/nginx'
        image = os.environ.get('IRIS_NGINX_TEST_IMAGE', 'iris-standalone-nginx:local')

        def docker(*args):
            result = subprocess.run(['docker', *args], capture_output=True, text=True)
            if result.returncode:
                self.fail(result.stderr)
            return result.stdout.strip()

        def start_service(address, generation):
            code = (
                'from http.server import BaseHTTPRequestHandler, HTTPServer\n'
                'import json\n'
                'class Handler(BaseHTTPRequestHandler):\n'
                ' def do_GET(self):\n'
                '  self.send_response(200); self.end_headers()\n'
                f'  self.wfile.write(json.dumps(dict(generation={generation}, path=self.path, '
                'host=self.headers.get("Host"), proto=self.headers.get("X-Forwarded-Proto"), '
                'upgrade=self.headers.get("Upgrade"))).encode())\n'
                'HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()\n'
            )
            docker('run', '-d', '--pull=never', '--name', service, '--network', network,
                   '--ip', address, '--network-alias', 'app', '--network-alias', 'frontend',
                   'python:3.12', 'python', '-u', '-c', code)

        def request(path):
            result = subprocess.run([
                'docker', 'exec', proxy, 'curl', '-ksSf', '--max-time', '2',
                '-H', 'Host: iris.example:18545', '-H', 'Origin: https://iris.example:18545',
                '-H', 'X-Forwarded-Proto: https', '-H', 'Upgrade: websocket',
                'https://127.0.0.1:8443' + path,
            ], capture_output=True, text=True)
            if result.returncode:
                return None
            try:
                return json.loads(result.stdout)
            except ValueError:
                return None

        def wait_for(path, generation):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                response = request(path)
                if response and response['generation'] == generation:
                    return response
                time.sleep(0.5)
            self.fail(f'nginx did not route {path} to service generation {generation} without reload')

        try:
            docker('network', 'create', network)
            subnet = json.loads(docker('network', 'inspect', network))[0]['IPAM']['Config'][0]['Subnet']
            addresses = ipaddress.ip_network(subnet)
            start_service(str(addresses[10]), 1)
            command = ('cp /fixture/nginx-newui.conf /etc/nginx/nginx.conf && '
                       'openssl req -x509 -nodes -newkey rsa:2048 -days 1 '
                       '-keyout /www/certs/key.pem -out /www/certs/cert.pem '
                       '-subj /CN=localhost >/dev/null 2>&1 && exec bash /fixture/entrypoint.sh')
            docker('run', '-d', '--pull=never', '--name', proxy, '--network', network,
                   '-v', f'{fixture.as_posix()}:/fixture:ro', '--entrypoint', '/bin/sh',
                   '-e', 'IRIS_UPSTREAM_SERVER=app', '-e', 'IRIS_UPSTREAM_PORT=8000',
                   '-e', 'IRIS_FRONTEND_SERVER=frontend', '-e', 'IRIS_FRONTEND_PORT=8000',
                   '-e', 'INTERFACE_HTTPS_PORT=8443', '-e', 'SERVER_NAME=localhost',
                   '-e', 'CERT_FILENAME=cert.pem', '-e', 'KEY_FILENAME=key.pem',
                   '-e', 'IRIS_CERT_RELOAD_INTERVAL=0', image, '-c', command)
            paths = ['/login?next=%2Falerts', '/socket.io/?EIO=4&transport=polling',
                     '/api/v2/alerts/1/artifacts?probe=1']
            for path in paths:
                response = wait_for(path, 1)
                self.assertEqual(response['path'], path)
                self.assertEqual(response['proto'], 'https')
            self.assertEqual(request(paths[1])['host'], 'iris.example:18545')
            self.assertEqual(request(paths[1])['upgrade'], 'websocket')
            docker('exec', proxy, 'nginx', '-t')
            docker('rm', '-f', service)
            start_service(str(addresses[11]), 2)
            for path in paths:
                self.assertEqual(wait_for(path, 2)['path'], path)
        finally:
            for name in (proxy, service):
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            subprocess.run(['docker', 'network', 'rm', network], capture_output=True)


if __name__ == '__main__':
    unittest.main()
