"""Initialize one standalone stack's persistent credentials and local TLS."""
import ipaddress
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
from urllib.parse import urlsplit


def public_hostname(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise ValueError('IRIS_PUBLIC_URL must be an HTTPS origin, e.g. https://iris.example:18545')
    parsed.port
    host = parsed.hostname.encode('idna').decode('ascii')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label) for label in host.split('.')):
            raise ValueError('Invalid public hostname')
    return host


def atomic_write(path, content, mode=0o600):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        os.chmod(temporary, mode)
        handle.write(content.encode())
    temporary.replace(path)


def initialize(directory, url):
    host = public_hostname(url)
    directory.mkdir(parents=True, exist_ok=True)
    env = directory / 'iris.env'
    if not env.exists():
        database_password = secrets.token_hex(32)
        broker_password = secrets.token_hex(32)
        broker = f'amqp://iris:{broker_password}@rabbitmq:5672//'
        values = {
            'POSTGRES_USER': 'postgres', 'POSTGRES_PASSWORD': database_password,
            'POSTGRES_ADMIN_USER': 'postgres', 'POSTGRES_ADMIN_PASSWORD': database_password,
            'POSTGRES_DB': 'iris_db', 'POSTGRES_SERVER': 'db', 'POSTGRES_PORT': '5432',
            'RABBITMQ_DEFAULT_USER': 'iris', 'RABBITMQ_DEFAULT_PASS': broker_password,
            'CELERY_BROKER': broker, 'SOCKETIO_MESSAGE_QUEUE': broker,
            'IRIS_SECRET_KEY': secrets.token_hex(32), 'IRIS_SECURITY_PASSWORD_SALT': secrets.token_hex(32),
            'IRIS_AUTHENTICATION_TYPE': 'local', 'IRIS_ADM_USERNAME': 'administrator',
            'IRIS_ADM_EMAIL': 'admin@localhost', 'IRIS_ADM_PASSWORD': secrets.token_hex(24),
            'IRIS_ADM_API_KEY': secrets.token_hex(32),
        }
        atomic_write(env, ''.join(f'{key}={value}\n' for key, value in values.items()))
    else:
        # Never silently rotate credentials of an existing database/broker.
        required = ('POSTGRES_PASSWORD', 'RABBITMQ_DEFAULT_PASS', 'IRIS_SECRET_KEY', 'IRIS_ADM_PASSWORD')
        existing = dict(line.split('=', 1) for line in env.read_text().splitlines() if '=' in line)
        if any(not existing.get(key) for key in required):
            raise RuntimeError('Existing runtime credentials are incomplete; restore the runtime volume backup')

    cert, key, marker = (directory / name for name in ('iris-cert.pem', 'iris-key.pem', 'tls-host'))
    fresh = cert.exists() and key.exists() and marker.exists() and marker.read_text() == host
    if fresh:
        fresh = subprocess.run(['openssl', 'x509', '-in', str(cert), '-checkend', '86400', '-noout'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not fresh:
        try:
            ipaddress.ip_address(host)
            san = f'IP:{host}'
        except ValueError:
            san = f'DNS:{host}'
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            new_key, new_cert = Path(temporary) / 'key.pem', Path(temporary) / 'cert.pem'
            subprocess.run(['openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048', '-sha256',
                            '-days', '365', '-keyout', str(new_key), '-out', str(new_cert),
                            '-subj', f'/CN={host}', '-addext', f'subjectAltName={san}'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chmod(new_key, 0o600)
            os.chmod(new_cert, 0o644)
            new_key.replace(key)
            new_cert.replace(cert)
        atomic_write(marker, host)


if __name__ == '__main__':
    os.umask(0o077)
    initialize(Path('/runtime'), os.environ.get('IRIS_PUBLIC_URL', 'https://localhost:18545'))
    print('Standalone credentials and TLS ready. Existing credentials retained; no secrets logged.')
