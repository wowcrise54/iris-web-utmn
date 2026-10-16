from iris_interface.IrisModuleInterface import IrisModuleInterface, IrisModuleTypes
from iris_interface.IrisInterfaceStatus import IIStatus, I2CodeSuccess

from app.db import db

from .client import OpenCTIClient, OpenCTIError
from .enrichment import enrich_iocs
from .storage import IrisStore, collect_targets, configuration, module_row, remove_hooks


AUTO_HOOKS = ('on_postload_alert_create', 'on_postload_alert_update',
              'on_postload_alert_merge', 'on_postload_alert_escalate', 'on_postload_alert_unmerge',
              'on_postload_ioc_create', 'on_postload_ioc_update',
              'on_postload_case_create', 'on_postload_case_update')
MANUAL_HOOKS = ('on_manual_trigger_alert', 'on_manual_trigger_case', 'on_manual_trigger_ioc')


class IrisOpenCTIInterface(IrisModuleInterface):
    _module_name = 'IRIS OpenCTI'
    _module_description = 'Optional exact IOC enrichment with OpenCTI threat context'
    _module_version = '1.0.0'
    _interface_version = '1.2.0'
    _module_type = IrisModuleTypes.module_processor
    _pipeline_support = False
    _pipeline_info = {}
    _default_enabled = False
    _module_configuration = [
        {'param_name': 'opencti_url', 'param_human_name': 'OpenCTI URL',
         'param_description': 'Base URL, without /graphql. TLS certificates are verified.',
         'default': None, 'mandatory': True, 'type': 'string'},
        {'param_name': 'opencti_token', 'param_human_name': 'OpenCTI API token',
         'param_description': 'Read-only service account. Never included in enrichment or logs.',
         'default': None, 'mandatory': True, 'type': 'sensitive_string'},
    ]

    def register_hooks(self, module_id):
        row = module_row(module_id)
        remove_hooks(module_id)
        if not row or not row.is_active:
            return
        config = configuration(row)
        try:
            OpenCTIClient(config.get('opencti_url'), config.get('opencti_token'),
                          is_active=IrisStore(config).active).check_connection()
            for hook in AUTO_HOOKS + MANUAL_HOOKS:
                status = self.register_to_hook(module_id, hook,
                    manual_hook_name='OpenCTI: refresh enrichment' if hook in MANUAL_HOOKS else None,
                    run_asynchronously=True)
                if status.is_failure():
                    raise OpenCTIError('hook_registration_error')
        except Exception as error:
            row.is_active = False
            db.session.commit()
            remove_hooks(module_id)
            if isinstance(error, OpenCTIError):
                raise
            raise OpenCTIError('hook_registration_error') from None

    def hooks_handler(self, hook_name, hook_ui_name, data):
        row = module_row()
        if not row or not row.is_active:
            return IIStatus(I2CodeSuccess, 'OpenCTI module disabled', data=data)
        config = configuration(row)
        store = IrisStore(config)
        iocs, cases = collect_targets(data)
        try:
            client = OpenCTIClient(config.get('opencti_url'), config.get('opencti_token'), is_active=store.active)
            enrich_iocs(iocs, store, client, force=hook_name in MANUAL_HOOKS)
            store.summarize(cases)
        except OpenCTIError as error:
            self.log.warning(str(error))
        return IIStatus(I2CodeSuccess, f'OpenCTI: processed {len(iocs)} IOC(s)', data=data,
                        logs=list(self.message_queue))
