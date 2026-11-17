"""Exercise DIM lifecycle against the shipped 1.2.0 interface, with IRIS adapters isolated."""
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from iris_opencti_module.client import OpenCTIError


class ModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wheel = Path(__file__).resolve().parents[3] / 'source/dependencies/iris_interface-1.2.0-py3-none-any.whl'
        sys.path.insert(0, str(wheel))
        def stub(name, **values):
            module = types.ModuleType(name)
            module.__dict__.update(values)
            return module
        cls.session = MagicMock()
        cls.adapters = patch.dict(sys.modules, {
            'app': stub('app'),
            'app.db': stub('app.db', db=types.SimpleNamespace(session=cls.session)),
            'app.models.alerts': stub('app.models.alerts', Alert=type('Alert', (), {})),
            'app.models.cases': stub('app.models.cases', Cases=type('Cases', (), {})),
            'app.models.iocs': stub('app.models.iocs', Ioc=type('Ioc', (), {})),
            'app.models.models': stub('app.models.models', IrisModule=type('IrisModule', (), {}), IrisModuleHook=type('IrisModuleHook', (), {})),
            'app.datamgmt.iris_engine.evidence_storage': stub('evidence_storage', EvidenceStorage=object),
            'app.datamgmt.manage.manage_srv_settings_db': stub('settings', get_server_settings_as_dict=lambda: {}),
            'app.iris_engine.module_handler.module_handler': stub('module_handler',
                deregister_from_hook=MagicMock(), get_mod_config_by_name=lambda name: types.SimpleNamespace(get_data=lambda: None), register_hook=MagicMock()),
            'celery': stub('celery', Task=type('Task', (), {'request_stack': []})),
        })
        cls.adapters.start()
        cls.interface = importlib.import_module('iris_opencti_module.IrisOpenCTIInterface')

    @classmethod
    def tearDownClass(cls):
        cls.adapters.stop()

    def setUp(self):
        self.module = object.__new__(self.interface.IrisOpenCTIInterface)
        self.module.log = MagicMock()
        self.module.message_queue = []
        self.row = types.SimpleNamespace(is_active=False, module_config=[
            {'param_name': 'opencti_url', 'value': 'https://cti.example'},
            {'param_name': 'opencti_token', 'value': 'secret'},
        ])

    def test_default_disabled_and_no_network_or_hook_bindings(self):
        self.assertFalse(self.module._default_enabled)
        with patch.object(self.interface, 'module_row', return_value=self.row), \
             patch.object(self.interface, 'remove_hooks') as remove, \
             patch.object(self.interface, 'OpenCTIClient') as client, \
             patch.object(self.module, 'register_to_hook') as register:
            self.module.register_hooks(7)
            remove.assert_called_once_with(7)
            client.assert_not_called()
            register.assert_not_called()

    def test_real_shipped_interface_can_instantiate_an_unregistered_module(self):
        with patch.object(self.interface, 'OpenCTIClient') as client:
            instance = self.interface.IrisOpenCTIInterface()
            self.assertTrue(instance.is_ready())
            self.assertEqual(instance.get_interface_version(), '1.2.0')
            client.assert_not_called()

    def test_enable_validates_connection_then_registers_only_async_hooks(self):
        self.row.is_active = True
        with patch.object(self.interface, 'module_row', return_value=self.row), \
             patch.object(self.interface, 'remove_hooks'), \
             patch.object(self.interface, 'OpenCTIClient') as client, \
             patch.object(self.module, 'register_to_hook') as register:
            register.return_value.is_failure.return_value = False
            self.module.register_hooks(7)
            client.return_value.check_connection.assert_called_once()
            self.assertEqual(register.call_count, len(self.interface.AUTO_HOOKS + self.interface.MANUAL_HOOKS))
            self.assertTrue(all(c.kwargs['run_asynchronously'] for c in register.call_args_list))

    def test_failed_enable_disables_and_removes_hooks(self):
        self.row.is_active = True
        with patch.object(self.interface, 'module_row', return_value=self.row), \
             patch.object(self.interface, 'remove_hooks') as remove, \
             patch.object(self.interface, 'OpenCTIClient') as client:
            client.return_value.check_connection.side_effect = OpenCTIError('unauthorized')
            with self.assertRaises(OpenCTIError):
                self.module.register_hooks(7)
            self.assertFalse(self.row.is_active)
            self.assertEqual(remove.call_count, 2)

    def test_queued_handler_rechecks_disabled_state(self):
        with patch.object(self.interface, 'module_row', return_value=self.row), \
             patch.object(self.interface, 'collect_targets') as collect:
            result = self.module.hooks_handler('on_postload_alert_create', None, [])
            self.assertTrue(result.is_success())
            collect.assert_not_called()
