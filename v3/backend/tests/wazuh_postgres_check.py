"""Run against a disposable PostgreSQL database; never against an IRIS database."""
import os
if os.environ.get('WAZUH_DISPOSABLE_TEST_DB') != 'yes':
    raise RuntimeError('Set WAZUH_DISPOSABLE_TEST_DB=yes only for an isolated disposable database')

import importlib.util
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

engine = create_engine('postgresql://postgres@127.0.0.1/iris_wazuh_test')
path = Path('/source/app/alembic/versions/utmn_wazuh01.py')
spec = importlib.util.spec_from_file_location('wazuh_migration_check', path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

with engine.begin() as connection:
    schema = 'wazuh_check_' + uuid4().hex
    connection.execute(text(f'CREATE SCHEMA {schema}'))
    connection.execute(text(f'SET search_path TO {schema}'))
    # Simulate models already created by IRIS's db.create_all before Alembic.
    connection.execute(text('CREATE TABLE wazuh_poll_state (source_key VARCHAR(64) PRIMARY KEY, started_at TIMESTAMP NOT NULL, watermark TIMESTAMP NOT NULL, last_poll TIMESTAMP NOT NULL)'))
    connection.execute(text('CREATE TABLE wazuh_receipt (source_key VARCHAR(64) NOT NULL, document_key VARCHAR(64) NOT NULL, alert_uuid UUID NOT NULL, PRIMARY KEY (source_key, document_key))'))
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()
    assert inspect(connection).has_table('wazuh_poll_state')
    assert inspect(connection).has_table('wazuh_receipt')
    fresh = 'wazuh_check_' + uuid4().hex
    connection.execute(text(f'CREATE SCHEMA {fresh}'))
    connection.execute(text(f'SET search_path TO {fresh}'))
    migration.upgrade()
    assert inspect(connection).has_table('wazuh_poll_state')
    assert inspect(connection).has_table('wazuh_receipt')
print('PostgreSQL migration after create_all passed')
