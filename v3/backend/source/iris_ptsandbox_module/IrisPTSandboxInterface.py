from iris_interface.IrisModuleInterface import IrisModuleInterface, IrisModuleTypes


class IrisPTSandboxInterface(IrisModuleInterface):
    _module_name = 'PT Sandbox'
    _module_description = 'Import existing PT Sandbox 5.39 task summaries through its built-in MCP server.'
    _module_version = '2.0.0'
    _interface_version = '1.2.0'
    _module_type = IrisModuleTypes.module_processor
    _pipeline_support = False
    _pipeline_info = {}
    _default_enabled = False
    _module_configuration = [
        {'param_name': 'sandbox_url', 'param_human_name': 'PT Sandbox MCP URL', 'type': 'string',
         'param_description': 'HTTPS address of the PT Sandbox 5.39 appliance; /mcp is optional.', 'mandatory': True, 'default': ''},
        {'param_name': 'sandbox_token', 'param_human_name': 'MCP read token', 'type': 'sensitive_string',
         'param_description': 'Encrypted at rest. Requires the PT Sandbox MCP read permission.', 'mandatory': True, 'default': ''},
        {'param_name': 'database', 'param_human_name': 'MCP database', 'type': 'string',
         'param_description': 'Use scans_v2 or scans_v2_repl.', 'mandatory': True, 'default': 'scans_v2'},
        {'param_name': 'verify_tls', 'param_human_name': 'Проверять TLS-сертификат (true / false)', 'type': 'bool',
         'param_description': 'true — проверять сертификат сервера; false — отключить проверку сертификата. HTTPS сохраняется.',
         'mandatory': False, 'default': True},
        {'param_name': 'ca_bundle', 'param_human_name': 'Trusted CA file (optional)', 'type': 'string',
         'param_description': 'PEM path on app and worker for an internal CA. Empty uses system trust.', 'mandatory': False, 'default': ''},
    ]

    def register_hooks(self, module_id):
        # Task summaries are imported on demand from the case API.
        return None
