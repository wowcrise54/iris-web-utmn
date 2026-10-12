"""Verified v2 -> v3 cutover; preserve the v2 volumes for rollback."""
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'iris-upgrade-2-4-29-fastapi'
BASE = ['docker-compose.upgrade-validation.yml', 'docker-compose.saved-data.yml']
LIVE = [*BASE, 'docker-compose.v3.yml', 'docker-compose.v3-live.yml']
DB = PROJECT + '-db-1'
APP = PROJECT + '-app-1'
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')
BACKUP = Path('D:/Diplom/backups') / ('iris-v3-cutover-' + STAMP)
PREFIX = 'iris-web-utmn-v3-' + STAMP

def run(*args, capture=True):
    result = subprocess.run(list(args), cwd=ROOT, check=True, text=True, encoding='utf-8',
                            stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ''

def docker(*args):
    return run('docker', *args)

def compose(files, *args):
    return docker('compose', '-p', PROJECT, *[item for file in files for item in ('-f', file)], *args)

def wait_for(container, health=False):
    for _ in range(120):
        info = json.loads(docker('inspect', container))[0]
        state = info['State']
        if health and state.get('Health', {}).get('Status') == 'healthy':
            return
        if not health and state.get('Running') and subprocess.run(['docker', 'exec', container, 'pg_isready', '-U', 'postgres'],
                                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            return
        if state.get('Status') == 'exited':
            raise RuntimeError(container + ' exited; inspect its logs before continuing')
        time.sleep(2)
    raise RuntimeError(container + ' did not become ready')

def query(container, statement):
    return json.loads(docker('exec', container, 'psql', '-U', 'postgres', '-d', 'iris_db', '-At', '-c', statement))

app_info = json.loads(docker('inspect', APP))[0]
db_info = json.loads(docker('inspect', DB))[0]
assert app_info['Config']['Labels']['com.docker.compose.project'] == PROJECT
assert 'docker-compose.v3.yml' not in app_info['Config']['Labels']['com.docker.compose.project.config_files'], 'Already switched to v3'
assert any(mount.get('Name') == 'iris-web-utmn_upgrade-db' for mount in db_info['Mounts'])
assert query(DB, 'SELECT to_json(count(*) >= 2) FROM cases')
assert query(DB, 'SELECT to_json(count(*) = 1) FROM cases WHERE case_id = 2')
assert query(DB, 'SELECT to_json(count(*) = 1) FROM alerts WHERE alert_id = 1')
assert 'Two-client Yjs edit, persistence and worker queue delivery passed' in (ROOT/'v3/frontend/realtime-probe.log').read_text(encoding='utf-8')
assert '53 passed' in (ROOT/'v3/native-tests-final.log').read_text(encoding='utf-8')
assert 'Browser acceptance passed' in (ROOT/'v3/frontend/browser-probe-final.log').read_text(encoding='utf-8')
BACKUP.mkdir()
(ROOT / 'v3/runtime').mkdir(exist_ok=True)
old_env = dict(value.split('=', 1) for value in app_info['Config']['Env'] if '=' in value)
live_env = {key: value for key, value in old_env.items()
            if key.startswith(('IRIS_', 'POSTGRES_', 'CELERY_')) or key in {'DOCKERIZED', 'LOG_LEVEL'}}
live_env.pop('IRIS_WORKER', None)
live_env.update(POSTGRES_SERVER='db', IRIS_ALLOW_ORIGIN='https://localhost:18543', IRIS_HOSTNAME='localhost',
                CELERY_BROKER='amqp://guest:guest@rabbitmq//', IRIS_SOCKETIO_MESSAGE_QUEUE='amqp://guest:guest@rabbitmq//')
assert not (ROOT / '.env.v3.live').exists(), 'Live configuration already exists; review the previous cutover state'
(ROOT / '.env.v3.live').write_text('\n'.join(f'{key}={value}' for key, value in sorted(live_env.items())) + '\n', encoding='utf-8')

override = '''services:
  db:
    env_file: !override [.env.v3.live]
    networks: !override [upgrade]
  rabbitmq:
    networks: !override [upgrade]
  app:
    env_file: !override [.env.v3.live]
    networks: !override [upgrade]
    ports: !override ["127.0.0.1:18082:8000"]
  worker:
    env_file: !override [.env.v3.live]
    networks: !override [upgrade]
  frontend:
    networks: !override [upgrade]
    environment:
      PUBLIC_EXTERNAL_API_URL: https://localhost:18543
      IRIS_ALLOW_ORIGIN: https://localhost:18543
  nginx:
    networks: !override [upgrade]
    ports: !override ["127.0.0.1:18543:8443"]
volumes:
'''
for suffix in ('db', 'downloads', 'templates', 'server-data'):
    override += f'  v3-{suffix}: {{external: true, name: {PREFIX}-{suffix}}}\n'
(ROOT/'docker-compose.v3-live.yml').write_text(override, encoding='utf-8')
docker('tag', app_info['Image'], 'iris-v2-rollback:' + STAMP)
print('Closing ingress and stopping v2 app/worker for a consistent snapshot', flush=True)
compose(BASE, 'stop', 'nginx', 'app', 'worker')
opened = False

try:
    baseline = {}
    for table in ['cases', 'alerts', 'client', 'notes', 'notes_group', 'case_assets', 'ioc', 'case_tasks',
                  'task_assignee', 'cases_events', 'case_received_file', 'data_store_file',
                  'custom_dashboard', 'custom_dashboard_widget']:
        if query(DB, f"SELECT to_json(to_regclass('public.{table}') IS NOT NULL)"):
            baseline[table] = query(DB, f'SELECT COALESCE(json_agg(t),\'[]\'::json) FROM "{table}" t')
    baseline['users'] = query(DB, 'SELECT json_agg(t) FROM (SELECT id, "user", password, active FROM "user") t')
    (ROOT/'v3/runtime/data-baseline.json').write_text(json.dumps(baseline, ensure_ascii=False), encoding='utf-8')
    for database in ('iris_db', 'iris_tasks'):
        temporary = f'/tmp/{database}-{STAMP}.dump'
        docker('exec', DB, 'pg_dump', '-U', 'postgres', '-d', database, '-Fc', '-f', temporary)
        assert 'TOC Entries' in docker('exec', DB, 'pg_restore', '--list', temporary)
        docker('cp', DB + ':' + temporary, str(BACKUP / (database + '.dump')))
    mounts = []
    for suffix, folder in [('downloads','downloads'),('templates','templates'),('server-data','server-data')]:
        mounts += ['--mount', f'type=volume,src=iris-web-utmn_upgrade-{suffix},dst=/saved/{folder},readonly']
    docker('run', '--rm', '--network', 'none', *mounts, '--mount', f'type=bind,src={BACKUP},dst=/backup',
           '--entrypoint', 'tar', 'iris-upgrade-db:local', '-czf', '/backup/file-volumes.tar.gz', '-C', '/saved', '.')
    run('tar.exe', '-czf', str(BACKUP/'workspace.tar.gz'), '--exclude=.git', '--exclude=node_modules',
        '--exclude=.svelte-kit', '--exclude=build', '--exclude=*.log', '-C', str(ROOT), '.')
    checksums = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in BACKUP.iterdir() if file.is_file()}
    (BACKUP/'sha256.json').write_text(json.dumps(checksums, indent=2), encoding='utf-8')
    print('Verified snapshots: ' + str(BACKUP), flush=True)
    for suffix in ('db', 'downloads', 'templates', 'server-data'):
        docker('volume', 'create', PREFIX + '-' + suffix)
    mounts = []
    for suffix in ('downloads', 'templates', 'server-data'):
        mounts += ['--mount', f'type=volume,src={PREFIX}-{suffix},dst=/saved/{suffix}']
    docker('run', '--rm', '--network', 'none', *mounts, '--mount', f'type=bind,src={BACKUP},dst=/backup,readonly',
           '--entrypoint', 'tar', 'iris-upgrade-db:local', '-xzf', '/backup/file-volumes.tar.gz', '-C', '/saved')
    maintenance = [*LIVE, 'docker-compose.v3-maintenance.yml']
    compose(maintenance, 'up', '-d', '--no-build', '--no-deps', 'db')
    wait_for(DB)
    docker('cp', str(ROOT/'v3/backend/docker/db/create_user.sh'), DB + ':/tmp/create-user.sh')
    docker('exec', DB, 'bash', '/tmp/create-user.sh')
    docker('exec', DB, 'createdb', '-U', 'postgres', 'iris_tasks')
    for database in ('iris_db', 'iris_tasks'):
        docker('cp', str(BACKUP/(database+'.dump')), DB+':/tmp/'+database+'.dump')
        docker('exec', DB, 'pg_restore', '--exit-on-error', '-U', 'postgres', '-d', database, '/tmp/'+database+'.dump')
    print('PG18 and file copies restored; applying v3 migrations without host ingress', flush=True)
    compose(maintenance, 'up', '-d', '--no-build', '--no-deps', 'app', 'frontend')
    wait_for(APP, health=True)
    wait_for(PROJECT+'-frontend-1', health=True)
    compare_env = dict(os.environ, IRIS_TARGET_DB=DB)
    result = subprocess.run(['python', '-X', 'utf8', str(ROOT/'v3/compare_data.py')], cwd=ROOT, env=compare_env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', check=True)
    (BACKUP/'data-verification.json').write_text((ROOT/'v3/data-comparison.json').read_text(encoding='utf-8'), encoding='utf-8')
    file_mounts = []
    for suffix in ('downloads', 'templates', 'server-data'):
        file_mounts += ['--mount', f'type=volume,src=iris-web-utmn_upgrade-{suffix},dst=/source/{suffix},readonly',
                        '--mount', f'type=volume,src={PREFIX}-{suffix},dst=/target/{suffix},readonly']
    files_report = docker('run', '--rm', '--network', 'none', *file_mounts,
                          '--mount', f'type=bind,src={ROOT / "v3"},dst=/checks,readonly',
                          '--entrypoint', 'python', 'iris-upgrade-2-4-29-fastapi:local', '/checks/compare_files.py')
    (BACKUP/'file-verification.json').write_text(files_report, encoding='utf-8')
    docker('cp', str(ROOT/'v3/probe_api.py'), APP+':/tmp/probe_api.py')
    docker('exec', '-e', 'IRIS_PROBE_URL=http://localhost:8000', '-e', 'IRIS_PROBE_REPORT=/tmp/api-probe.json',
           APP, 'python', '/tmp/probe_api.py')
    print('Data and API verification passed; opening the original address', flush=True)
    opened = True
    compose(LIVE, 'up', '-d', '--no-build', '--no-deps', 'app', 'frontend', 'nginx', 'worker')
    wait_for(APP, health=True)
    wait_for(PROJECT+'-nginx-1', health=True)
    state = {'project': PROJECT, 'compose_files': LIVE, 'address': 'https://localhost:18543',
             'backup': str(BACKUP), 'volumes_prefix': PREFIX, 'version': 'v3.0.0-beta.6'}
    (ROOT/'v3/cutover-result.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    print(json.dumps(state, indent=2), flush=True)
except Exception:
    if opened:
        print('Failure after ingress opened: stopping writes and preserving PG18 for recovery', flush=True)
        compose(LIVE, 'stop', 'app', 'nginx', 'worker')
        raise
    print('Cutover failed before acceptance; restoring v2 using its preserved volumes', flush=True)
    compose(LIVE, 'stop', 'app', 'frontend', 'nginx', 'worker')
    compose(BASE, 'up', '-d', '--no-build', '--pull', 'never', 'db', 'app', 'worker', 'nginx')
    raise
