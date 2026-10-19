"""Run only against the disposable offline PostgreSQL verification container.

Uses an isolated transaction/schema; validates real PostgreSQL DDL and the actual
worker functions with a deterministic provider and no configured external service.
"""
import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import Mock
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.exc import IntegrityError

SOURCE = Path(os.environ.get('IRIS_SOURCE', '/iriswebapp'))

def extract(path, name, scope):
    nodes = ast.parse(path.read_text()).body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), scope)
    return scope[name]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    engine = create_engine('postgresql+psycopg2://postgres@127.0.0.1/postgres')
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = 'evidence_check_' + uuid4().hex
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            connection.execute(text('CREATE TABLE cases (case_id bigint PRIMARY KEY)'))
            connection.execute(text('CREATE TABLE "user" (id bigint PRIMARY KEY, active boolean)'))
            connection.execute(text('CREATE TABLE case_chat_conversation (id bigint PRIMARY KEY, case_id bigint, user_id bigint, archived_at timestamp, resolved_restriction_level integer, resolved_policy_id bigint)'))
            connection.execute(text('CREATE TABLE case_chat_message (id bigserial PRIMARY KEY, conversation_id bigint, role text, content jsonb)'))
            migration = load(SOURCE / 'app/alembic/versions/utmn_evidence01_analysis_jobs.py', 'evidence_migration_test')
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
            connection.execute(text('INSERT INTO cases VALUES (1)'))
            connection.execute(text('INSERT INTO "user" VALUES (2, true)'))
            connection.execute(text('INSERT INTO case_chat_conversation VALUES (3,1,2,NULL,0,NULL)'))
            insert = "INSERT INTO evidence_analysis(case_id,requested_by,kind,source_key,source) VALUES(1,2,'pcap','pcap:file=1','{}') RETURNING id"
            first = connection.execute(text(insert)).scalar_one()
            savepoint = connection.begin_nested()
            try:
                connection.execute(text(insert))
            except IntegrityError:
                savepoint.rollback()
            else:
                raise AssertionError('Active-source deduplication failed')
            connection.execute(text("UPDATE evidence_analysis SET status='completed' WHERE id=:id"), {'id': first})
            connection.execute(text(insert))
            connection.execute(text('DELETE FROM evidence_analysis'))
            # Map only the actual columns; no application bootstrap, no production settings.
            Base = declarative_base()
            from sqlalchemy import Table, MetaData
            metadata = MetaData()
            class Job(Base):
                __table__ = Table('evidence_analysis', metadata, autoload_with=connection)
            class User(Base):
                __table__ = Table('user', metadata, autoload_with=connection)
            class Conversation(Base):
                __table__ = Table('case_chat_conversation', metadata, autoload_with=connection)
            class Message(Base):
                __table__ = Table('case_chat_message', metadata, autoload_with=connection)
            session = Session(bind=connection, join_transaction_mode='create_savepoint')
            class QueryProperty:
                def __get__(self, instance, owner): return session.query(owner)
            Job.query = QueryProperty()
            db = SimpleNamespace(session=session)
            app_stub = ModuleType('app')
            app_stub.socket_io = SimpleNamespace(emit=Mock())
            sys.modules['app'] = app_stub
            base = load(SOURCE / 'app/iris_engine/llm/providers/base.py', 'evidence_base_schema_test')
            sys.modules['app.iris_engine.llm.providers.base'] = base
            summary = load(SOURCE / 'app/iris_engine/evidence/summary.py', 'evidence_summary_schema_test')
            redaction = load(SOURCE / 'app/iris_engine/llm/redaction.py', 'evidence_redaction_schema_test')
            diagnostics = load(SOURCE / 'app/iris_engine/llm/diagnostics.py', 'evidence_diag_schema_test')
            calls, audits = [], []
            broken = [False]
            def provider_stream(**kwargs):
                calls.append(kwargs)
                assert kwargs['max_tokens'] in (1024,2048)
                yield base.TextDelta('partial findings' if broken[0] else 'Derived findings sandbox:1:log:9 offset 0')
                if broken[0]:
                    yield base.Error('HTTP 502', provider_code='http_502', http_status=502)
                else:
                    yield base.MessageEnd('end_turn', prompt_tokens=10, completion_tokens=10)
            def append_message(**kwargs):
                m = Message(conversation_id=kwargs['conversation'].id, role=kwargs['role'], content=kwargs['content'])
                session.add(m); session.flush(); return m
            def audit(**kwargs):
                audits.append(kwargs); return SimpleNamespace(id=len(audits))
            biz = SimpleNamespace(record_egress=audit, finalise_egress=Mock(), sum_tokens_today=lambda **kw:0, append_message=append_message)
            config = SimpleNamespace(enabled=True, provider='test', model='m', redact_ips=True, redact_emails=False, redact_hashes=False,
                                     daily_token_budget_per_user=0,daily_token_budget_org=0)
            queue=[]
            scope = dict(db=db,EvidenceAnalysis=Job,User=User,CaseChatConversation=Conversation,CaseChatMessage=Message,
                         ROLE_ASSISTANT='assistant',CaseAccessLevel=SimpleNamespace(read_only=1,full_access=2),
                         ac_fast_check_user_has_case_access=lambda *args:True,dt=dt,hashlib=hashlib,json=json,
                         load_config=lambda **kw:config,get_llm_provider=lambda cfg:SimpleNamespace(name='test',stream_completion=provider_stream),
                         resolve_for_conversation=lambda c:SimpleNamespace(policy=None,restriction_level=0),
                         provider_events=diagnostics.provider_events,TextDelta=base.TextDelta,MessageEnd=base.MessageEnd,Error=base.Error,
                         redact_text=redaction.redact_text,summary_messages=summary.summary_messages,SUMMARY_TOKENS=1024,FINAL_TOKENS=2048,
                         case_chat=biz,log=__import__('logging').getLogger('evidence.check'))
            tasks = SOURCE / 'app/iris_engine/evidence/tasks.py'
            for fn in ('authorized','summarize','publish','process_analysis'):
                extract(tasks,fn,scope)
            process=scope['process_analysis']
            process.apply_async=lambda **kw:queue.append(kw)
            process.delay=lambda identifier:queue.append(identifier)
            task_module = ModuleType('app.iris_engine.evidence.tasks')
            task_module.process_analysis=process
            sys.modules['app.iris_engine.evidence.tasks']=task_module
            scope['BusinessProcessingError']=ValueError
            retry=extract(SOURCE / 'app/business/evidence_analysis.py','retry_job',scope)
            scope['evidence_pages']=lambda job:([{'source':'sandbox:1:log:9','offset':0,'end_offset':20,'text':'raw evidence 10.1.2.3'}],[])
            job=Job(case_id=1,requested_by=2,conversation_id=3,kind='sandbox',source_key='sandbox:1',source={'scan_id':1},result={})
            session.add(job);session.commit()
            broken[0]=True
            process(job.id);session.refresh(job)
            assert job.status=='failed' and job.result['partial_response']=='partial findings'
            assert session.query(Message).count()==1
            broken[0]=False;retry(job)
            process(job.id);session.refresh(job)
            assert job.status=='queued' and job.progress==1 and 'partial_response' not in job.result
            process(job.id);session.refresh(job)
            assert job.status=='completed'
            assert session.query(Message).count()==1, 'Continuation must update the partial message'
            assert all('raw evidence' not in json.dumps(m.content) for m in session.query(Message))
            assert '10.1.2.3' not in json.dumps([c['messages'][0].content for c in calls])
            assert all('raw evidence' not in json.dumps(a.get('request_snapshot')) for a in audits)
            # Revoked access prevents another provider call.
            job.status='queued';session.get(User,2).active=False;session.commit();old=len(calls)
            process(job.id);session.refresh(job)
            assert job.status=='failed' and len(calls)==old
            connection.execute(text('DELETE FROM cases WHERE case_id=1'))
            assert connection.execute(text('SELECT count(*) FROM evidence_analysis')).scalar_one()==0
            session.close()
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            print('Evidence migration and worker: idempotent upgrade, active deduplication, 502 partial persistence, resume, redaction, bounded summaries, revoked access, case cascade and downgrade passed')
        finally:
            transaction.rollback()

if __name__=='__main__':main()
