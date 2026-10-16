from iris_interface.IrisModuleInterface import IrisModuleInterface, IrisModuleTypes


class IrisPTSandboxInterface(IrisModuleInterface):
    _module_name = 'PT Sandbox'
    _module_description = ('PT Sandbox 5.37: file checks from cases and /sandbox check in war rooms. '
                           'Background analysis, separate chat verdict, original report/logs and Yuki analysis. '
                           'Files leave IRIS for the configured appliance. Logs may be sent to the Yuki provider on request.')
    _module_version = '1.0.0'
    _interface_version = '1.2.0'
    _module_type = IrisModuleTypes.module_processor
    _pipeline_support = False
    _pipeline_info = {}
    _default_enabled = False
    _module_configuration = [
        {'param_name': 'sandbox_url', 'param_human_name': 'PT Sandbox HTTPS URL', 'type': 'string',
         'param_description': 'PT Sandbox 5.37 appliance; /api/v1 is optional. TLS is verified.', 'mandatory': True, 'default': ''},
        {'param_name': 'sandbox_token', 'param_human_name': 'API token', 'type': 'sensitive_string',
         'param_description': 'Encrypted at rest. Allow file checks, reports and log downloads for this source.', 'mandatory': True, 'default': ''},
        {'param_name': 'image_id', 'param_human_name': 'VM image ID', 'type': 'string',
         'param_description': 'Required for behavioral analysis. Check connection to list available images.', 'mandatory': True, 'default': ''},
        {'param_name': 'analysis_duration', 'param_human_name': 'Analysis duration (seconds)', 'type': 'string',
         'param_description': '10–600 seconds.', 'mandatory': True, 'default': '120'},
        {'param_name': 'max_file_mb', 'param_human_name': 'Maximum file size (MiB)', 'type': 'string',
         'param_description': '1–512 MiB, also limited by the appliance.', 'mandatory': True, 'default': '100'},
        {'param_name': 'ca_bundle', 'param_human_name': 'Trusted CA file (optional)', 'type': 'string',
         'param_description': 'PEM path on app and worker for an internal CA. Empty uses system trust.', 'mandatory': False, 'default': ''},
    ]

    def register_hooks(self, module_id):
        # Manual file checks use the case API, never automatic upload hooks.
        return None
