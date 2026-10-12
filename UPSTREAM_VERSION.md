# Active IRIS v3.0.0-beta.6 with native FastAPI and EN/RU

The active application is now built from `v3/backend` and `v3/frontend`.
The old `source` tree is preserved for recovery. See `v3/README.md` and the
current four-file Compose command in `AGENTS.md`.

Pinned upstream commits: meta `cc172b492a271114b4ff4340abe273ee072f306f`,
backend `77ec7a3a6932e970fdf18632d66d962c97e388be`,
frontend `d1a6aa38b3b4fda5a7fb0d9ccf981e0a91c29f5d`.

## Preserved v2.4.29 baseline

Upstream: https://github.com/dfir-iris/iris-web/releases/tag/v2.4.29

Source commit: `340ce04080806a83837b713d01ea70632ee2b3f7`.

The official release's application code, templates, static resources, database
models and migrations are used. Framework imports and startup wiring are adapted
to FastAPI/Uvicorn, standalone SQLAlchemy/Marshmallow/WTForms, signed sessions and
native ASGI Socket.IO. Uploaded image-store files are served by ASGI StaticFiles.
The release's HTML sanitization and dashboard code are retained.
The release's image and Word libraries retain their original versions; two
removed `collections` aliases are restored from `collections.abc` for Python 3.12.

This release ships static frontend files in `source/app/static`; it does not use
the beta branch's `ui` build, API v2 or GraphQL HTTP endpoints.

`tests/migration/contracts.json` is generated from the immutable official tag,
covering 411 route definitions and hashes for 815 UI/static files.
`business_contracts.json` covers the AST of 213 existing Python files, ignoring
framework imports and the `FlaskForm` → `WebForm` provider-name change.
The Alembic environment additionally uses an explicit SQLAlchemy 2 transaction
so startup migrations persist both schema changes and the installed revision.
This single transaction adaptation is normalized in the AST comparison and
covered by a separate persisted-revision regression test.

Local configuration and administrator credentials are retained in `.env`.
Primary Docker volumes are kept. Before this upgrade, source/configuration, all
databases and uploaded/template/server-data files were backed up under
`D:/Diplom/backups`; the prior working image is tagged
`iriswebapp_app:before-2.4.29`.

Acceptance commands, results and practical validation limits are documented in
`tests/upgrade_2_4_29/README.md`.
