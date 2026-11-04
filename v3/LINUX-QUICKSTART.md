# Standalone Linux deployment

From the repository root, with Docker Engine and Docker Compose installed:

```bash
docker compose -p iris-standalone -f docker-compose.standalone.yml up -d --build
```

This single Compose file builds backend, worker, frontend and nginx from source.
The backend starts from public Python images; no locally built IRIS v2 image,
other Compose files, host env file, prepared certificates or external volumes
are required. PostgreSQL 18 and RabbitMQ use their public images.

The initialization service generates database/broker passwords, IRIS keys and a
self-signed TLS certificate inside the persistent `runtime` volume. Its secret
file has mode 600. Restarts keep credentials; the certificate is refreshed when
its hostname changes or it approaches expiry. App initialization runs migrations
before the worker starts. OpenCTI is installed disabled by default.

By default nginx publishes HTTPS on port 18545 on all host interfaces. Open
`https://localhost:18545` when using a browser on that host. For access from
another computer, specify the server's actual IP or DNS name before starting:

```bash
export IRIS_PUBLIC_URL=https://192.0.2.10:18545  # replace with your server address
docker compose -p iris-standalone -f docker-compose.standalone.yml up -d --build
```

The public URL is used consistently for browser API calls, backend origin checks
and the certificate's hostname/IP SAN. Use the same value on later deployments.
`IRIS_BIND_ADDRESS` defaults to `0.0.0.0`; set it to `127.0.0.1` for tunnel-only
access. `IRIS_HTTPS_PORT` defaults to `18545`; if changed, update the port in
`IRIS_PUBLIC_URL` too. Only nginx is published; database, broker and backend
remain on the private Compose network. The generated certificate is self-signed,
so the browser will ask you to trust it. The host firewall must permit the port
when using direct network access.

Check progress:

The `init` service exiting with code 0 is normal; the other services stay running.

```bash
docker compose -p iris-standalone -f docker-compose.standalone.yml ps -a
docker compose -p iris-standalone -f docker-compose.standalone.yml logs --tail 100 init app worker nginx
```

Initial username: `administrator`. Read its generated password locally:

```bash
docker compose -p iris-standalone -f docker-compose.standalone.yml exec app \
  sh -c '. /runtime/iris.env; printf "%s\n" "$IRIS_ADM_PASSWORD"'
```

Keep the `runtime`, database, broker and file volumes when updating or stopping
the stack; back up runtime credentials with the database and files. A new project
name creates a separate installation with separate volumes. This profile creates
a fresh database and does not import the Windows deployment's data.

The earlier `docker-compose.v3-linux.yml` is retained as a legacy overlay. The
standalone command above replaces the old multi-file quickstart for new hosts.
