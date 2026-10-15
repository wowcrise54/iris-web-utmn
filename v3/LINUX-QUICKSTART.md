# Fresh Linux deployment

This guide creates a **new, empty** v3 database and file volumes. It does not
import the Windows data volumes and must not be combined with
`docker-compose.saved-data.yml` or `docker-compose.v3-live.yml`.

From the repository root:

```bash
bash scripts/create-v3-linux-env.sh

mkdir -p tests/upgrade_2_4_29/runtime/certs
if [[ ! -s tests/upgrade_2_4_29/runtime/certs/upgrade-key.pem || \
      ! -s tests/upgrade_2_4_29/runtime/certs/upgrade-cert.pem ]]; then
  umask 077
  openssl req -x509 -nodes -newkey rsa:2048 -days 7 \
    -keyout tests/upgrade_2_4_29/runtime/certs/upgrade-key.pem \
    -out tests/upgrade_2_4_29/runtime/certs/upgrade-cert.pem \
    -subj /CN=localhost \
    -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
fi

export V3_VOLUME_PREFIX=iris-opencti-linux
```

Build the local v2 base image referenced by `Dockerfile.native`, then the v3
application and its UI. The Linux overlay clears the inherited PostgreSQL 12
build, uses PostgreSQL 18, takes DB credentials only from the generated file,
and lets Compose create project-specific volumes.

```bash
docker compose -p iris-opencti-linux \
  -f docker-compose.upgrade-validation.yml \
  build app

docker compose -p iris-opencti-linux \
  -f docker-compose.upgrade-validation.yml \
  -f docker-compose.v3.yml \
  -f docker-compose.v3-linux.yml \
  build app worker frontend nginx

docker compose -p iris-opencti-linux \
  -f docker-compose.upgrade-validation.yml \
  -f docker-compose.v3.yml \
  -f docker-compose.v3-linux.yml \
  up -d --no-build

docker compose -p iris-opencti-linux \
  -f docker-compose.upgrade-validation.yml \
  -f docker-compose.v3.yml \
  -f docker-compose.v3-linux.yml \
  ps
```

Open `https://localhost:18545` on the Linux host. The bootstrap admin username
is `administrator`; its generated password is in the mode-600 `.env.v3.validation`
file. Keep that file on the host and back it up securely: the same PostgreSQL
password, IRIS session key and encryption key are required after restart. The
certificate is self-signed and the nginx ports bind to loopback by default. For
remote access, use an SSH tunnel such as `ssh -L 18545:127.0.0.1:18545 srvadmin@HOST`.

After first login, configure the OpenCTI URL and read-only API token under
Settings → Modules and enable **IRIS OpenCTI**. It is installed disabled by default.
