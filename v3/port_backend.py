"""Apply infrastructure-only changes to the pinned IRIS v3 backend."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'v3/backend'
APP = BACKEND / 'source/app'
for name in ('web.py', 'extensions.py', 'auth_login.py', 'web_forms.py', 'legacy_collections.py'):
    shutil.copy2(ROOT / 'source/app' / name, APP / name)

imports = {
    'from flask import Flask': 'from app.web import IRISApp as Flask',
    'from flask import ': 'from app.web import ',
    'from flask_login import ': 'from app.auth_login import ',
    'from flask_bcrypt import ': 'from app.extensions import ',
    'from flask_caching import ': 'from app.extensions import ',
    'from flask_marshmallow import ': 'from app.extensions import ',
    'from flask_socketio import ': 'from app.socket_transport import ',
    'from flask_sqlalchemy.pagination import ': 'from app.extensions import ',
    'from flask_sqlalchemy.query import ': 'from app.extensions import ',
    'from flask_sqlalchemy import ': 'from app.extensions import ',
    'from flask_wtf import FlaskForm': 'from app.web_forms import WebForm as FlaskForm',
}
for file in (BACKEND / 'source/app').rglob('*.py'):
    text = file.read_text(encoding='utf-8')
    for original, replacement in imports.items():
        text = text.replace(original, replacement)
    file.write_text(text, encoding='utf-8', newline='\n')

file = APP / '__init__.py'
text = file.read_text(encoding='utf-8')
text = text.replace('import os\n', 'import os\nfrom app import legacy_collections\n', 1)
text = text.replace('app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)',
                    '# Forwarded headers are handled by Uvicorn on the internal trusted proxy network.')
text = text.replace("_socket_kwargs.update(socket_io_queue_kwargs(app.config.get('SOCKETIO_MESSAGE_QUEUE')))",
                    "_socket_kwargs['message_queue'] = app.config.get('SOCKETIO_MESSAGE_QUEUE')")
text = text.replace('socket_io = SocketIO(app, **_socket_kwargs)',
                    'socket_io = SocketIO(app, **_socket_kwargs)\nasgi_app = socket_io.asgi_app')
text = text.replace('dropzone = Dropzone(app)',
                    'from app.web_forms import init_forms\ninit_forms(app)\ndropzone = Dropzone(app)')
file.write_text(text, encoding='utf-8', newline='\n')

# Preserve the installed local revision as an ancestor of v3's IOC migration.
legacy = 'e5d79b8c4a55_add_custom_dashboards_tables.py'
shutil.copy2(ROOT / 'source/app/alembic/versions' / legacy, APP / 'alembic/versions' / legacy)
file = APP / 'alembic/versions/3715d4fac4de_add_link_between_case_and_ioc.py'
text = file.read_text(encoding='utf-8').replace("down_revision = 'd5a720d1b99b'", "down_revision = 'e5d79b8c4a55'")
file.write_text(text, encoding='utf-8', newline='\n')

file = BACKEND / 'source/requirements.txt'
lines = file.read_text(encoding='utf-8').splitlines()
excluded = ('Flask', 'flask-', 'gunicorn', 'gevent', 'psycogreen', 'sentry-sdk[flask]')
lines = [line for line in lines if not line.startswith(excluded)]
lines += ['fastapi==0.115.6', 'uvicorn[standard]==0.34.0', 'starlette==0.41.3',
          'Jinja2==3.1.5', 'itsdangerous==2.2.0', 'python-multipart==0.0.20',
          'bcrypt==4.2.1', 'cachelib==0.13.0', 'python-socketio==5.17.0',
          'aio-pika>=9.4,<10', 'sentry-sdk[fastapi]>=2.20,<3']
file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
file = APP / 'iris_engine/observability/reporter.py'
text = file.read_text(encoding='utf-8').replace('from sentry_sdk.integrations.flask import FlaskIntegration',
                                             'from sentry_sdk.integrations.fastapi import FastApiIntegration')
text = text.replace("FlaskIntegration(transaction_style='endpoint')", 'FastApiIntegration()')
file.write_text(text, encoding='utf-8', newline='\n')
print('Pinned v3 backend: native FastAPI imports and migration ancestry prepared')
