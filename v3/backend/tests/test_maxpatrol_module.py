"""Shipped DIM interface compatibility and migration SQL generation."""
import ast
import importlib
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from alembic.migration import MigrationContext
from alembic.operations import Operations

SOURCE = Path(__file__).resolve().parents[1] / 'source'


def stub(name, **values):
    module = types.ModuleType(name)
    module.__dict__.update(values)
    return module


class ModuleTests(unittest.TestCase):
    def test_shipped_interface_instantiates_disabled_without_network(self):
        wheel = SOURCE / 'dependencies/iris_interface-1.2.0-py3-none-any.whl'
        adapters = {
            'app': stub('app'),
            'app.datamgmt.iris_engine.evidence_storage': stub('evidence', EvidenceStorage=object),
            'app.datamgmt.manage.manage_srv_settings_db': stub('settings', get_server_settings_as_dict=lambda: {}),
            'app.iris_engine.module_handler.module_handler': stub('handler',
                deregister_from_hook=Mock(), register_hook=Mock(),
                get_mod_config_by_name=lambda _name: types.SimpleNamespace(get_data=lambda: None)),
            'celery': stub('celery', Task=type('Task', (), {'request_stack': []})),
        }
        with patch.object(sys, 'path', [str(SOURCE), str(wheel), *sys.path]), \
                patch.dict(sys.modules, adapters), patch('requests.Session') as session:
            interface = importlib.import_module('iris_maxpatrol_module.IrisMaxPatrolInterface')
            instance = interface.IrisMaxPatrolInterface()
            self.assertTrue(instance.is_ready())
            self.assertFalse(instance._default_enabled)
            self.assertFalse(instance.is_providing_pipeline())
            self.assertEqual(instance.get_module_type(), 'module_processor')
            self.assertEqual(instance.get_interface_version(), '1.2.0')
            instance.register_hooks(1)
            session.assert_not_called()

    def test_migration_generates_only_additive_postgresql_tables(self):
        path = SOURCE / 'app/alembic/versions/utmn_maxpatrol01.py'
        spec = importlib.util.spec_from_file_location('maxpatrol_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        output = io.StringIO()
        context = MigrationContext.configure(dialect_name='postgresql',
            opts={'as_sql': True, 'output_buffer': output})
        with Operations.context(context):
            migration.upgrade()
        sql = output.getvalue()
        self.assertIn('CREATE TABLE maxpatrol_receipt', sql)
        self.assertIn('PRIMARY KEY (source_key, incident_id)', sql)
        self.assertIn('CREATE TABLE maxpatrol_poll_state', sql)
        self.assertNotIn('DROP ', sql)
        self.assertNotIn('UPDATE ', sql)
        self.assertNotIn('DELETE ', sql)

    def test_worker_import_and_default_registration_are_wired(self):
        configuration = ast.parse((SOURCE / 'app/configuration.py').read_text(encoding='utf-8'))
        values = [node.value for node in ast.walk(configuration) if isinstance(node, ast.Constant)]
        self.assertIn('app.iris_engine.maxpatrol.tasks', values)
        post_init = ast.parse((SOURCE / 'app/post_init.py').read_text(encoding='utf-8'))
        values = [node.value for node in ast.walk(post_init) if isinstance(node, ast.Constant)]
        self.assertIn('iris_maxpatrol_module', values)


if __name__ == '__main__':
    unittest.main()
