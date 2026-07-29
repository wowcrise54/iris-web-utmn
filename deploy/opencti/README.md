# Local OpenCTI for DFIR-IRIS

This is a resource-conscious local OpenCTI deployment for development. It
contains OpenCTI, one worker, Elasticsearch, Redis, MinIO, and RabbitMQ. An
optional AlienVault OTX connector imports Indicators and Observables from
Pulses modified during the configured lookback period.

The OpenCTI UI is bound to `http://127.0.0.1:4000`. Dependency ports are not
published. The OpenCTI service also joins the external `iris_backend` network,
where DFIR-IRIS reaches it as `http://opencti:8080`.

## Start

```powershell
.\Initialize-OpenCTI.ps1
docker compose pull
docker compose up -d
docker compose ps
```

## AlienVault OTX

Create a free OTX API key at `https://otx.alienvault.com`, then set it in the
ignored `.env` file:

```dotenv
ALIENVAULT_API_KEY=replace-with-your-otx-api-key
```

`ALIENVAULT_PULSE_START_TIMESTAMP` controls the initial import boundary. New
configurations default to one month before initialization. Start the optional
connector with:

```powershell
docker compose --profile alienvault pull connector-alienvault
docker compose --profile alienvault up -d connector-alienvault
docker compose --profile alienvault logs -f connector-alienvault
```

After the initial import, the connector checks OTX hourly and continues from
its stored state.

## Credentials

Credentials and the API token are generated in the ignored `.env` file.

```powershell
Get-Content .env |
    Where-Object { $_ -match '^OPENCTI_ADMIN_(EMAIL|PASSWORD)=' }
```

## Stop

```powershell
docker compose stop
```

To remove containers while preserving OpenCTI data:

```powershell
docker compose down
```

Do not use `docker compose down -v` unless all local OpenCTI data should be
permanently deleted.
