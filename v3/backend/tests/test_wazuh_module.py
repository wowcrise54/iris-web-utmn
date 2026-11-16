"""Verify that IRIS can register Wazuh without starting collection."""
import importlib
import sys
import types
from unittest.mock import Mock, patch

from test_maxpatrol_module import SOURCE, stub


def test_wazuh_module_registers_disabled_with_expected_configuration():
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
        interface = importlib.import_module('iris_wazuh_module.IrisWazuhInterface')
        module = interface.IrisWazuhInterface()
        assert module.is_ready()
        assert not module._default_enabled
        assert not module.is_providing_pipeline()
        assert module.get_module_type() == 'module_processor'
        parameters = {p['param_name']: p for p in module.get_init_configuration()}
        assert parameters['password']['type'] == 'sensitive_string'
        assert parameters['index']['default'] == 'wazuh-alerts-4.x-*'
        assert parameters['min_level']['default'] == '12'
        assert parameters['verify_tls']['default'] is True
        assert {'url', 'username', 'customer_id', 'severity_id', 'status_id', 'interval', 'timeout'} <= parameters.keys()
        module.register_hooks(1)
        session.assert_not_called()
