import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Table, create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship, scoped_session, sessionmaker


Base = declarative_base()
case_alerts = Table('case_alerts', Base.metadata, Column('case_id', ForeignKey('cases.case_id')), Column('alert_id', ForeignKey('alerts.alert_id')))
alert_iocs = Table('alert_iocs', Base.metadata, Column('alert_id', ForeignKey('alerts.alert_id')), Column('ioc_id', ForeignKey('ioc.ioc_id')))


class Cases(Base):
    __tablename__ = 'cases'
    case_id = Column(Integer, primary_key=True)
    client_id = Column(Integer)
    custom_attributes = Column(JSON)
    alerts = relationship('Alert', secondary=case_alerts, back_populates='cases')


class Alert(Base):
    __tablename__ = 'alerts'
    alert_id = Column(Integer, primary_key=True)
    alert_customer_id = Column(Integer)
    cases = relationship(Cases, secondary=case_alerts, back_populates='alerts')
    iocs = relationship('Ioc', secondary=alert_iocs, back_populates='alerts')


class IocType(Base):
    __tablename__ = 'ioc_type'
    type_id = Column(Integer, primary_key=True)
    type_name = Column(String)


class Ioc(Base):
    __tablename__ = 'ioc'
    ioc_id = Column(Integer, primary_key=True)
    ioc_value = Column(String)
    case_id = Column(ForeignKey(Cases.case_id))
    ioc_type_id = Column(ForeignKey(IocType.type_id))
    ioc_enrichment = Column(JSONB().with_variant(JSON(), 'sqlite'))
    case = relationship(Cases)
    ioc_type = relationship(IocType)
    alerts = relationship(Alert, secondary=alert_iocs, back_populates='iocs')


class IrisModule(Base):
    __tablename__ = 'modules'
    id = Column(Integer, primary_key=True)
    module_name = Column(String)
    is_active = Column(Integer)
    module_config = Column(JSON)


class IrisModuleHook(Base):
    __tablename__ = 'hooks'
    id = Column(Integer, primary_key=True)
    module_id = Column(Integer)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = scoped_session(sessionmaker(bind=self.engine))
        Base.query = self.session.query_property()
        self.db = SimpleNamespace(session=self.session, engine=self.engine)
        def stub(name, **values):
            module = ModuleType(name)
            module.__dict__.update(values)
            return module
        adapters = {
            'app': stub('app'), 'app.db': stub('app.db', db=self.db),
            'app.models.alerts': stub('alerts', Alert=Alert), 'app.models.cases': stub('cases', Cases=Cases),
            'app.models.iocs': stub('iocs', Ioc=Ioc), 'app.models.models': stub('models', IrisModule=IrisModule, IrisModuleHook=IrisModuleHook),
        }
        location = Path(__file__).resolve().parents[1] / 'iris_opencti_module/storage.py'
        spec = importlib.util.spec_from_file_location('iris_opencti_module.storage_fixture', location)
        self.storage = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, adapters):
            spec.loader.exec_module(self.storage)
        self.session.add(IrisModule(id=1, module_name='iris_opencti_module', is_active=1, module_config=[]))
        self.kind = IocType(type_id=1, type_name='domain')
        self.case = Cases(case_id=1, client_id=7, custom_attributes={'existing': {'value': 'preserve'}})
        self.alert = Alert(alert_id=2, alert_customer_id=7, cases=[self.case])
        self.first = Ioc(ioc_id=1, ioc_value='example.org', ioc_type=self.kind, case=self.case, alerts=[self.alert])
        self.second = Ioc(ioc_id=2, ioc_value='another.org', ioc_type=self.kind, alerts=[self.alert])
        self.session.add_all([self.case, self.first, self.second])
        self.session.commit()

    def test_manual_ioc_target_is_scoped_to_the_current_case(self):
        import ast
        location = Path(__file__).resolve().parents[3] / 'source/app/datamgmt/dim_hooks.py'
        tree = ast.parse(location.read_text(encoding='utf-8'))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == '_TARGET_LOADERS' for t in node.targets))
        namespace = {'Ioc': Ioc}
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(location), 'exec'), namespace)
        loader = namespace['_TARGET_LOADERS']['ioc']
        self.assertIs(loader(1, 1), self.first)
        self.assertIsNone(loader(1, 999))

    def tearDown(self):
        self.session.remove()
        self.engine.dispose()

    def test_case_collection_includes_own_and_linked_alert_iocs_once(self):
        iocs, cases = self.storage.collect_targets([self.case, self.alert, self.first])
        self.assertEqual({x.ioc_id for x in iocs}, {1, 2})
        self.assertEqual(cases, {1})
        store = self.storage.IrisStore({})
        self.assertEqual(store.scope(self.first), [7])
        self.assertEqual(store.scope(self.second), [7])

    def test_summary_includes_linked_only_ioc_and_preserves_custom_attributes(self):
        self.first.ioc_enrichment = {'opencti': {'status': 'matched', 'input': {'type': 'domain', 'value': 'example.org'}}}
        self.session.commit()
        self.storage.IrisStore({}).summarize({1})
        self.assertEqual(self.case.custom_attributes['existing'], {'value': 'preserve'})
        result = json.loads(self.case.custom_attributes['__iris_opencti']['value'])
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['counts'], {'matched': 1, 'not_checked': 1})
        self.assertEqual(result['iocs'][1]['alert_ids'], [2])

    def test_stale_result_for_changed_ioc_is_not_counted_as_match(self):
        self.first.ioc_enrichment = {'opencti': {'status': 'matched', 'input': {'type': 'domain', 'value': 'old.org'}}}
        self.session.commit()
        self.storage.IrisStore({}).summarize({1})
        result = json.loads(self.case.custom_attributes['__iris_opencti']['value'])
        self.assertEqual(result['counts'], {'not_checked': 2})

    def test_postgres_update_is_provider_only_and_guards_original_input(self):
        session = MagicMock()
        result = {'status': 'no_match', 'input': {'type': 'domain', 'value': 'example.org'}}
        with patch.object(self.storage.db, 'session', session):
            self.storage.IrisStore({}).save(self.first, result)
        statement = session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        self.assertIn('jsonb_set', sql)
        self.assertIn('ioc_type.type_name', sql)
        self.assertNotIn('SET ioc_value', sql)
        self.assertIn('example.org', compiled.params.values())

    def test_postgres_lock_is_released_after_lookup_failure(self):
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.scalar.return_value = True
        with patch.object(self.storage.db, 'engine', engine), self.assertRaises(ValueError):
            with self.storage.IrisStore({}).lock('key'):
                raise ValueError('lookup failed')
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertIn('pg_try_advisory_lock', statements[0])
        self.assertIn('pg_advisory_unlock', statements[-1])

    def test_persistent_cache_filters_status_and_time(self):
        self.first.ioc_enrichment = {'opencti': {'status': 'matched', 'cache_key': 'same', 'checked_at': '2026-10-15T01:00:00+00:00'}}
        self.second.ioc_enrichment = {'opencti': {'status': 'timeout', 'cache_key': 'error', 'checked_at': '2026-10-15T01:00:00+00:00'}}
        self.session.commit()
        store = self.storage.IrisStore({})
        self.assertEqual(store.cached('same', '2026-10-14T00:00:00+00:00')['status'], 'matched')
        self.assertIsNone(store.cached('same', '2026-10-16T00:00:00+00:00'))
        self.assertIsNone(store.cached('error', '2026-10-14T00:00:00+00:00'))
