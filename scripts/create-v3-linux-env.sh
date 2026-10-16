#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -e .env.v3.validation ]]; then
  printf '%s\n' '.env.v3.validation already exists; leaving it unchanged.' >&2
  exit 1
fi
command -v openssl >/dev/null || { printf '%s\n' 'openssl is required.' >&2; exit 1; }

umask 077
db_password="$(openssl rand -hex 32)"
cat > .env.v3.validation <<EOF
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${db_password}
POSTGRES_ADMIN_USER=postgres
POSTGRES_ADMIN_PASSWORD=${db_password}
POSTGRES_DB=iris_db
POSTGRES_SERVER=db
POSTGRES_PORT=5432
CELERY_BROKER=amqp://rabbitmq
IRIS_SOCKETIO_MESSAGE_QUEUE=amqp://rabbitmq
IRIS_SECRET_KEY=$(openssl rand -hex 32)
IRIS_SECURITY_PASSWORD_SALT=$(openssl rand -hex 32)
IRIS_AUTHENTICATION_TYPE=local
IRIS_ADM_USERNAME=administrator
IRIS_ADM_EMAIL=admin@localhost
IRIS_ADM_PASSWORD=$(openssl rand -hex 24)
IRIS_ADM_API_KEY=$(openssl rand -hex 32)
IRIS_HOSTNAME=localhost
IRIS_ALLOW_ORIGIN=https://localhost:18545
DEMO_MODE=false
EOF
chmod 600 .env.v3.validation
printf '%s\n' 'Created .env.v3.validation with fresh secrets (mode 600).'
