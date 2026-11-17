"""Real ORM/worker/chat round trip against a fake appliance in a rolled-back schema."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker

import app as app_module
from app import app
from app.db import db
from app.configuration import SQLALCHEMY_BASE_ADMIN_URI, PG_DB_
from app.business import ptsandbox as business
from app.models.models import IrisModule
from app.models.sandbox import SandboxScan, SandboxLog
from app.models.war_rooms import WarRoomChatMessage
from app.iris_engine.ptsandbox import tasks
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
    original_root = app.config['DATASTORE_PATH']
    with tempfile.TemporaryDirectory(prefix='ptsb-fixture-') as directory, engine.connect() as connection, app.app_context():
        transaction = connection.begin()
        session = scoped_session(sessionmaker(bind=connection, join_transaction_mode='create_savepoint'))
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            for table, key in (('cases', 'case_id'), ('data_store_file', 'file_id'), ('war_room', 'war_room_id'),
                               ('iris_module', 'id'), ('user', 'id'), ('war_room_chat_message', 'message_id')):
                connection.execute(text(f'CREATE TABLE "{table}" (LIKE public."{table}" INCLUDING DEFAULTS)'))
                connection.execute(text(f'ALTER TABLE "{table}" ADD PRIMARY KEY ({key})'))
            connection.execute(text('CREATE TABLE war_room_case (LIKE public.war_room_case INCLUDING DEFAULTS)'))
            connection.execute(text('CREATE SEQUENCE fixture_chat_id'))
            connection.execute(text("ALTER TABLE war_room_chat_message ALTER COLUMN message_id SET DEFAULT nextval('fixture_chat_id')"))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            connection.execute(text("INSERT INTO cases(case_id,client_id,name) VALUES(1,1,'Sandbox fixture')"))
            connection.execute(text('INSERT INTO "user"(id,"user",name,active) VALUES(3,\'fixture\',\'Fixture\',true)'))
            connection.execute(text("INSERT INTO war_room(war_room_id,name,state) VALUES(5,'Fixture','open')"))
            connection.execute(text('INSERT INTO war_room_case(war_room_id,case_id) VALUES(5,1)'))
            sample = Path(directory) / 'sample.bin'
            sample.write_bytes(b'benign integration fixture')
            connection.execute(text("INSERT INTO data_store_file(file_id,file_original_name,file_local_name,file_parent_id,added_by_user_id,file_case_id) VALUES(2,'sample.bin',:path,1,3,1)"), {'path': str(sample)})
            db.session = session
            app.config['DATASTORE_PATH'] = directory
            config = []
            for parameter in IrisPTSandboxInterface._module_configuration:
                entry = dict(parameter)
                entry['value'] = {'sandbox_url': 'https://sandbox.invalid', 'sandbox_token': encrypt_secret('fixture-token'),
                                  'image_id': 'fixture-vm'}.get(entry['param_name'], entry['default'])
                if entry['param_name'] == 'sandbox_url':
                    entry['connection_check'] = {'ok': True}
                config.append(entry)
            db.session.add(IrisModule(id=4, added_by_id=3, module_name=business.MODULE, module_config=config, is_active=True))
            db.session.commit()
            original_log = gzip.compress(b'{"process":"fixture.exe","event":"test"}\n')
            log_uri = 'sha256:' + hashlib.sha256(original_log).hexdigest()
            report = {'scan_id': str(uuid4()), 'result': {'verdict': 'DANGEROUS', 'scan_state': 'FULL', 'threat': 'TEST'},
                      'vendor_extension': {'retained': True}, 'artifacts': [{'engine_results': [{'details': {'sandbox': {
                          'logs': [{'file_uri': log_uri, 'file_name': 'normalized.json.gz', 'type': 'EVENT_NORMALIZED'}]}}}]}]}
            fake = Mock()
            fake.check_connection.return_value = {'version_matches': True}
            fake.upload.return_value = 'sfm:temporary'
            fake.start.return_value = report['scan_id']

            def response(path, **kwargs):
                if path == 'analysis/checkTask':
                    return {'result': report['result'], 'is_preflight': False}
                if path == 'analysis/report':
                    return report
                if path == 'storage/downloadArtifact':
                    assert kwargs['payload']['file_uri'] == log_uri
                    return original_log
                raise AssertionError(path)
            fake.request.side_effect = response
            with patch.object(tasks.process_scan, 'delay'), patch.object(tasks.process_scan, 'apply_async'), \
                 patch.object(tasks, 'client_from_config', return_value=fake), \
                 patch.object(tasks, 'ac_fast_check_user_has_case_access', return_value=True), \
                 patch.object(tasks, 'ac_fast_check_user_has_war_room_access', return_value=True), \
                 patch.object(app_module, 'socket_io', Mock()):
                created = business.start_scan(1, 2, 3, confirmed=True, war_room_id=5)
                tasks.process_scan.run(created['id'])
                assert db.session.get(SandboxScan, created['id']).status == 'running'
                tasks.process_scan.run(created['id'])
            scan = db.session.get(SandboxScan, created['id'])
            assert scan.status == 'completed'
            assert scan.report['vendor_extension']['retained'] is True
            log = SandboxLog.query.filter_by(scan_id=scan.id).one()
            assert log.content == original_log
            assert 'fixture.exe' in business.text_page(log)['text']
            message = WarRoomChatMessage.query.filter_by(message_id=scan.notification_id).one()
            assert message.kind == 'system' and 'DANGEROUS' in message.body and 'Logs: 1/1' in message.body
            assert 'fixture-token' not in message.body
            assert fake.upload.call_count == fake.start.call_count == 1
            print('PT Sandbox workflow: file → queued → running → full report → original gzip log → separate chat message → Yuki text page passed (fake appliance)')
        finally:
            session.remove()
            db.session = original_session
            app.config['DATASTORE_PATH'] = original_root
            transaction.rollback()
    engine.dispose()
    print('All fixture tables and data rolled back; public application data was outside the search path')


if __name__ == '__main__':
    main()
