from iris_interface.IrisModuleInterface import IrisModuleInterface, IrisModuleTypes


def param(name, label, default, kind='string', mandatory=True):
    return {'param_name': name, 'param_human_name': label, 'default': default,
            'param_description': '', 'mandatory': mandatory, 'type': kind}


class IrisWazuhInterface(IrisModuleInterface):
    _module_name = 'Wazuh Indexer'
    _module_description = 'Import Wazuh alerts into IRIS.'
    _module_version = '1.0.0'
    _interface_version = '1.2.0'
    _module_type = IrisModuleTypes.module_processor
    _pipeline_support = False
    _pipeline_info = {}
    _default_enabled = False
    _module_configuration = [
        param('url', 'Indexer HTTPS URL', ''),
        param('username', 'Indexer username', ''),
        param('password', 'Indexer password', '', 'sensitive_string'),
        param('index', 'Index pattern', 'wazuh-alerts-4.x-*'),
        param('customer_id', 'IRIS customer ID', '1'),
        param('severity_id', 'IRIS severity ID', '1'),
        param('status_id', 'IRIS status ID', '5'),
        param('interval', 'Polling interval (seconds)', '30'),
        param('timeout', 'Timeout (seconds)', '30'),
        param('min_level', 'Minimum Wazuh level', '12'),
        param('verify_tls', 'Verify TLS certificate', True, 'bool', False),
    ]

    def register_hooks(self, module_id):
        return None
