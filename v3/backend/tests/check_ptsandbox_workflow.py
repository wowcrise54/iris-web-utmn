"""Real ORM import against a fake MCP appliance in a rolled-back schema."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker

from app import app
from app.db import db
from app.configuration import SQLALCHEMY_BASE_ADMIN_URI, PG_DB_
from app.business import ptsandbox as business
from app.models.models import IrisModule
from app.models.sandbox import SandboxScan, SandboxLog
from app.iris_engine.mail.secrets import encrypt_secret
from iris_ptsandbox_module.IrisPTSandboxInterface import IrisPTSandboxInterface


def main():
    schema = 'iris_ptsb_flow_' + uuid4().hex
    engine = create_engine(SQLALCHEMY_BASE_ADMIN_URI + PG_DB_)
    migration = Path(__file__).parents[1] / 'source/app/alembic/versions/utmn_sandbox01_pt_sandbox.py'
    spec = importlib.util.spec_from_file_location('ptsandbox_workflow_migration', migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_session = db.session
    with engine.connect() as connection, app.app_context():
        transaction = connection.begin()
        session = scoped_session(sessionmaker(bind=connection, join_transaction_mode='create_savepoint'))
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            for table, key in (('cases', 'case_id'), ('data_store_file', 'file_id'), ('war_room', 'war_room_id'),
                               ('iris_module', 'id'), ('user', 'id')):
                connection.execute(text(f'CREATE TABLE "{table}" (LIKE public."{table}" INCLUDING DEFAULTS)'))
                connection.execute(text(f'ALTER TABLE "{table}" ADD PRIMARY KEY ({key})'))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            connection.execute(text("INSERT INTO cases(case_id,client_id,name) VALUES(1,1,'Sandbox fixture')"))
            connection.execute(text('INSERT INTO "user"(id,"user",name,active) VALUES(3,\'fixture\',\'Fixture\',true)'))
            db.session = session
            config = []
            for parameter in IrisPTSandboxInterface._module_configuration:
                entry = dict(parameter)
                entry['value'] = {'sandbox_url': 'https://sandbox.invalid', 'sandbox_token': encrypt_secret('fixture-token')}.get(entry['param_name'], entry['default'])
                if entry['param_name'] == 'sandbox_url':
                    entry['connection_check'] = {'ok': True, 'transport': 'mcp'}
                config.append(entry)
            db.session.add(IrisModule(id=4, added_by_id=3, module_name=business.MODULE, module_config=config, is_active=True))
            db.session.commit()
            original_log = gzip.compress(b'{"process":"fixture.exe","event":"test"}\n')
            old = SandboxScan(case_id=1, file_name='historical.bin', status='completed',
                              report={'result': {'verdict': 'CLEAN'}})
            db.session.add(old)
            db.session.flush()
            db.session.add(SandboxLog(scan_id=old.id, file_uri='sha256:' + hashlib.sha256(original_log).hexdigest(),
                                      name='normalized.json.gz', kind='EVENT_NORMALIZED', content=original_log))
            db.session.commit()

            scan_id = str(uuid4())
            start = '2026-11-19T10:21:18Z'
            fake = Mock(url='https://sandbox.invalid/mcp')
            fake.task_sql.side_effect = business.SandboxClient.task_sql
            row = {'start': '2026-11-19 10:21:18', 'sid': scan_id, 'status': 'SUCCESS',
                   'object_name': 'fixture.pdf', 'verdict': 'CLEAN', 'priority': 200}
            fake.query.side_effect = [[{**row, 'verdict_is_final': 0}], [{**row, 'verdict_is_final': 1}]]
            with patch.object(business, 'client_from_config', return_value=fake):
                created = business.import_scan(1, scan_id, start, 3)
                assert created['status'] == 'preliminary'
                updated = business.import_scan(1, scan_id, start, 3)
            assert updated['id'] == created['id'] and updated['status'] == 'completed'
            imported = business.projection(db.session.get(SandboxScan, created['id']), detail=True)
            assert imported['remote_task']['priority'] == 200 and imported['verdict'] == 'CLEAN'
            assert business.projection(old, detail=True)['logs'] == []
            assert all('FROM scans_v2.tasks FINAL' in call.args[0] and scan_id in call.args[0]
                       for call in fake.query.call_args_list)
            print('MCP import: preliminary → final, duplicate-free reimport and legacy log exclusion passed')
        finally:
            session.remove()
            db.session = original_session
            transaction.rollback()
    engine.dispose()
    print('All fixture tables and data rolled back; public application data was outside the search path')


if __name__ == '__main__':
    main()
