"""Capture configuration privately and create COPY volumes for the v3 rehearsal."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, encoding='utf-8').strip()

info = json.loads(docker('inspect', 'iris-upgrade-2-4-29-fastapi-app-1'))[0]
labels = info['Config']['Labels']
assert labels['com.docker.compose.project'] == 'iris-upgrade-2-4-29-fastapi'
assert 'docker-compose.saved-data.yml' in labels['com.docker.compose.project.config_files']
env = dict(item.split('=', 1) for item in info['Config']['Env'] if '=' in item)
needed = {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_ADMIN_USER', 'POSTGRES_ADMIN_PASSWORD',
          'POSTGRES_DB', 'IRIS_SECRET_KEY', 'IRIS_SECURITY_PASSWORD_SALT', 'IRIS_AUTHENTICATION_TYPE',
          'IRIS_ADM_PASSWORD', 'IRIS_ADM_API_KEY'}
config = {key: env[key] for key in needed if key in env}
config.update(POSTGRES_SERVER='db', POSTGRES_PORT='5432', CELERY_BROKER='amqp://guest:guest@rabbitmq//',
              IRIS_HOSTNAME='localhost', IRIS_ALLOW_ORIGIN='https://localhost:18545,https://localhost:18543',
              IRIS_SOCKETIO_MESSAGE_QUEUE='amqp://guest:guest@rabbitmq//', DEMO_MODE='False')
env_file = root / '.env.v3.validation'
if env_file.exists():
    raise SystemExit('Validation env already exists; inspect it without printing secrets before replacing')
env_file.write_text('\n'.join(f'{key}={value}' for key, value in sorted(config.items())) + '\n', encoding='utf-8')
for suffix in ('db', 'downloads', 'templates', 'server-data'):
    name = 'iris-v3-validation-20261010-' + suffix
    docker('volume', 'create', name)
print('Private validation env and four independent volumes created')
