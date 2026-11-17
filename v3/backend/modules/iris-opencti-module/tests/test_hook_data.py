import importlib.util
from pathlib import Path
import unittest
import ast
from types import SimpleNamespace
from unittest.mock import MagicMock
import base64
import pickle

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base


HELPER = Path(__file__).resolve().parents[3] / 'source/app/iris_engine/module_handler/hook_data.py'
Base = declarative_base()


class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True)
    value = Column(String)


class HookDataTests(unittest.TestCase):
    def test_optional_default_disabled_is_applied_before_hook_registration(self):
        location = HELPER.parent / 'module_handler.py'
        tree = ast.parse(location.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'register_module')
        for opt_in in (False, True):
            row = SimpleNamespace(id=7, is_active=True)
            metadata = SimpleNamespace(**{name: (lambda: '') for name in (
                'get_module_name', 'get_module_description', 'get_module_version', 'get_interface_version',
                'is_providing_pipeline', 'pipeline_get_info')},
                get_init_configuration=lambda: [], get_module_type=lambda: 'module_processor',
                register_hooks=MagicMock())
            if opt_in:
                metadata._default_enabled = False
            observed = []
            metadata.register_hooks.side_effect = lambda **kwargs: observed.append(row.is_active)
            namespace = {'logger': MagicMock(), 'instantiate_module_from_name': lambda **kwargs: (metadata, ''),
                         'iris_module_exists': lambda **kwargs: False, 'preset_init_mod_config': lambda value: value,
                         'iris_module_add': lambda **kwargs: row, 'db': SimpleNamespace(session=MagicMock())}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(location), 'exec'), namespace)
            result, message = namespace['register_module']('iris_opencti_module')
            self.assertIs(result, row)
            self.assertEqual(observed, [not opt_in])

    def test_broker_failure_does_not_fail_the_original_save(self):
        location = HELPER.parent / 'module_handler.py'
        tree = ast.parse(location.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'call_modules_hook')
        models = {name: MagicMock() for name in ('IrisHook', 'IrisModule', 'IrisModuleHook')}
        models['IrisModuleHook'].query.with_entities.return_value.filter.return_value.join.return_value.all.return_value = [
            SimpleNamespace(run_asynchronously=True, module_name='iris_opencti_module', manual_hook_ui_name=None)
        ]
        task = MagicMock()
        task.delay.side_effect = RuntimeError('broker offline')
        namespace = {**models, 'and_': MagicMock(), 'logger': MagicMock(), 'base64': base64,
                     'dumps': pickle.dumps, 'hmac_sign': lambda payload: b'signature',
                     'task_hook_wrapper': task, 'iris_current_user': None,
                     '_call_builtin_hook_listeners': MagicMock()}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(location), 'exec'), namespace)
        data = {'alert_id': 1}
        self.assertIs(namespace['call_modules_hook']('on_postload_alert_create', data), data)
        namespace['logger'].exception.assert_called_once()

    def test_unmerge_notifies_the_former_case_for_summary_refresh(self):
        location = HELPER.parents[2] / 'business/alerts.py'
        tree = ast.parse(location.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'alerts_unmerge')
        unit = ast.Module(body=[ast.parse('from __future__ import annotations').body[0], function], type_ignores=[])
        case, alert = SimpleNamespace(case_id=7), SimpleNamespace(alert_id=3)
        hook = MagicMock()
        namespace = {'get_case': lambda identifier: case, 'unmerge_alert_from_case': lambda *args: (True, 'done'),
                     'track_activity': MagicMock(), 'add_obj_history_entry': MagicMock(), 'call_modules_hook': hook}
        exec(compile(unit, str(location), 'exec'), namespace)
        namespace['alerts_unmerge'](alert, 7)
        hook.assert_any_call('on_postload_case_update', case, caseid=7)

    def test_worker_reloads_current_rows_without_overwriting_them(self):
        spec = importlib.util.spec_from_file_location('hook_data', HELPER)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            item = Item(id=1, value='queued snapshot')
            session.add(item)
            session.commit()
            session.expunge(item)
            current = session.get(Item, 1)
            current.value = 'edited since enqueue'
            session.commit()
            result = helper.reload_hook_data(item, session)
            self.assertEqual(result[0].value, 'edited since enqueue')
            self.assertEqual(session.get(Item, 1).value, 'edited since enqueue')
            session.delete(current)
            session.commit()
            self.assertEqual(helper.reload_hook_data(item, session), [])
            self.assertEqual(helper.reload_hook_data({'id': 1}, session), [{'id': 1}])
