"""Run inside the app container: HTTP smoke test with a temporary local provider.

Reads the existing administrator key in memory; never prints it or saves settings.
"""
import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from app import app
from app.iris_engine.llm.client import get_llm_provider, load_config
from app.iris_engine.llm.providers.base import ChatMessage, MessageEnd, TextDelta
from app.models.authorization import User


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, data, content_type='application/json'):
        raw = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        assert self.path == '/api/v1/models', self.path
        self.send(200, {'data': [{'id': 'allowed'}, {'id': 'denied'}]})

    def do_POST(self):
        assert self.path == '/api/v1/chat/completions', self.path
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if body['model'] == 'denied':
            self.send(403, {'error': {'message': 'provider-private-error'}})
        elif body.get('stream'):
            self.send(200, 'data: ' + json.dumps({'choices': [{'delta': {'content': 'OK'}, 'finish_reason': None}]}) +
                      '\n\ndata: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}) +
                      '\n\ndata: [DONE]\n\n', 'text/event-stream')
        else:
            assert body['messages'] == [{'role': 'user', 'content': 'Reply OK.'}]
            self.send(200, {'choices': [{'message': {'content': 'OK'}}]})


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    session = requests.Session()
    session.trust_env = False
    endpoint = 'http://127.0.0.1:8000/api/v2/manage/case-chat/provider/check'
    try:
        with app.app_context():
            admin = User.query.filter_by(user='administrator', active=True).first()
            assert admin and admin.api_key, 'Existing admin API key required'
            headers = {'Authorization': f'Bearer {admin.api_key}'}
            before = load_config()
        body = dict(provider='custom', base_url=f'http://127.0.0.1:{server.server_port}/api/v1',
                    model='allowed', api_key='smoke-only')
        assert session.post(endpoint, json=body, timeout=10).status_code in (401, 403)
        allowed = session.post(endpoint, headers=headers, json=body, timeout=10)
        assert allowed.status_code == 200, (allowed.status_code, allowed.text[:200])
        assert allowed.json()['model_accessible'] is True, allowed.json()
        assert allowed.json()['models'] == ['allowed', 'denied']
        denied = session.post(endpoint, headers=headers, json=body | {'model': 'denied'}, timeout=10)
        assert denied.json()['model_accessible'] is False
        assert denied.json()['model_error'] == 'http_403'
        assert 'provider-private-error' not in denied.text
        listed = session.post(endpoint, headers=headers, json=body | {'model': ''}, timeout=10)
        assert listed.json()['model_accessible'] is None
        assert session.post(endpoint, headers=headers, json=[], timeout=10).status_code == 400
        adapter = get_llm_provider(replace(before, enabled=True, **body))
        events = list(adapter.stream_completion(model='allowed', system='',
                      messages=[ChatMessage(role='user', content=[{'type': 'text', 'text': 'Hello'}])], tools=[]))
        assert any(isinstance(event, TextDelta) and event.text == 'OK' for event in events)
        assert isinstance(events[-1], MessageEnd)
        with app.app_context():
            assert load_config() == before, 'Provider check changed saved configuration'
        print('PASS: admin auth, model listing, allowed/denied access, no-secret errors, '
              'unsaved config, /api/v1 streaming; saved settings unchanged')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
