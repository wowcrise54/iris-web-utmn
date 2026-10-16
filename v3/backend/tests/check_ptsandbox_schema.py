"""Validate the migration in a transactionally isolated schema, always rolled back.

Run in a configured IRIS app container. No production tables/data are touched.
"""
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.configuration import SQLALCHEMY_BASE_ADMIN_URI, PG_DB_


def main():
    migration = Path(__file__).parents[1] / 'source/app/alembic/versions/utmn_sandbox01_pt_sandbox.py'
    spec = importlib.util.spec_from_file_location('ptsandbox_migration_check', migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = 'iris_ptsb_check_' + uuid4().hex
    engine = create_engine(SQLALCHEMY_BASE_ADMIN_URI + PG_DB_)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            for table, key in (('cases', 'case_id'), ('data_store_file', 'file_id'),
                               ('war_room', 'war_room_id'), ('iris_module', 'id')):
                connection.execute(text(f'CREATE TABLE {table} ({key} bigint PRIMARY KEY)'))
            connection.execute(text('CREATE TABLE "user" (id bigint PRIMARY KEY)'))
            for statement in ('INSERT INTO cases VALUES (1)', 'INSERT INTO data_store_file VALUES (2)',
                              'INSERT INTO "user" VALUES (3)', 'INSERT INTO iris_module VALUES (4)'):
                connection.execute(text(statement))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
                module.upgrade()  # Native bootstrap may have already created the model tables.
            insert = "INSERT INTO sandbox_scan(case_id,file_id,requested_by,module_id,file_name,status) VALUES(1,2,3,4,'sample','queued') RETURNING id"
            first = connection.execute(text(insert)).scalar_one()
            savepoint = connection.begin_nested()
            try:
                connection.execute(text(insert))
            except IntegrityError:
                savepoint.rollback()
            else:
                raise AssertionError('Concurrent active checks were not rejected')
            connection.execute(text("UPDATE sandbox_scan SET status='completed' WHERE id=:id"), {'id': first})
            second = connection.execute(text(insert)).scalar_one()
            assert second != first
            connection.execute(text("INSERT INTO sandbox_log(scan_id,file_uri,name,kind,content) VALUES(:id,'sha256:test','trace','EVENT_RAW',:data)"),
                               {'id': first, 'data': b'original evidence'})
            assert bytes(connection.execute(text('SELECT content FROM sandbox_log')).scalar_one()) == b'original evidence'
            connection.execute(text('DELETE FROM data_store_file WHERE file_id=2'))
            assert connection.execute(text('SELECT count(*) FROM sandbox_scan WHERE file_id IS NULL')).scalar_one() == 2
            connection.execute(text('DELETE FROM cases WHERE case_id=1'))
            assert connection.execute(text('SELECT count(*) FROM sandbox_scan')).scalar_one() == 0
            assert connection.execute(text('SELECT count(*) FROM sandbox_log')).scalar_one() == 0
            with Operations.context(MigrationContext.configure(connection)):
                module.downgrade()
            print('PT Sandbox schema: migration, unique active check, binary log storage and cascades passed')
        finally:
            transaction.rollback()
    engine.dispose()
    print('Temporary schema rolled back; production tables were outside the search path')


if __name__ == '__main__':
    main()
