from iris_interface.IrisModuleInterface import IrisModuleInterface, IrisModuleTypes
from iris_maxpatrol_module.collector import LOOKBACK_DESCRIPTION


def parameter(name, label, default, description='', mandatory=True, kind='string'):
    return {'param_name': name, 'param_human_name': label, 'default': default,
            'param_description': description, 'mandatory': mandatory, 'type': kind}


class IrisMaxPatrolInterface(IrisModuleInterface):
    _module_name = 'MaxPatrol SIEM'
    _module_description = 'Automatic MaxPatrol incident ingestion as IRIS alerts, with persistent deduplication.'
    _module_version = '1.0.0'
    _interface_version = '1.2.0'
    _module_type = IrisModuleTypes.module_processor
    _pipeline_support = False
    _pipeline_info = {}
    _default_enabled = False
    _module_configuration = [
        parameter('siem_url', 'MaxPatrol SIEM HTTPS URL', '', 'Example: https://siem.example.org'),
        parameter('api_token', 'API token', '', 'Encrypted at rest; use an account allowed to read incidents and events.',
                  kind='sensitive_string'),
        parameter('customer_id', 'IRIS customer ID', '1'),
        parameter('interval', 'Polling interval (seconds)', '30', '1–86400; worker checks due sources every 5 seconds.'),
        parameter('lookback_hours', 'Lookback (hours)', '72', LOOKBACK_DESCRIPTION),
        parameter('timeout', 'HTTP request timeout (seconds)', '60', '1–600 per API request.'),
        parameter('severity_id', 'IRIS alert severity ID', '1', 'Default matches the supplied exporter.'),
        parameter('status_id', 'IRIS alert status ID', '5', 'Default matches the supplied exporter.'),
        parameter('verify_tls', 'Проверять TLS-сертификат (true / false)', True,
                  'Disable only for appliances whose certificate cannot be verified.', mandatory=False, kind='bool'),
    ]

    def register_hooks(self, module_id):
        # Polling is registered once by the worker; activation is checked in each cycle.
        return None
