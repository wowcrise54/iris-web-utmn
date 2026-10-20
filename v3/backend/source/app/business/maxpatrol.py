"""Native module settings and transactional incident ingestion."""
import copy
from datetime import datetime, timezone
from uuid import UUID, uuid5

from app.db import db
from app.models.errors import BusinessProcessingError
from app.models.models import IrisModule
from app.models.maxpatrol import MaxPatrolReceipt
from app.iris_engine.mail.secrets import encrypt_secret, decrypt_secret
from iris_maxpatrol_module.collector import Config, positive_int

MODULE = 'iris_maxpatrol_module'
NAMESPACE = UUID('dc32cd4f-0440-4f48-b09e-e3aeb86cf716')


def configuration(row):
    values = {p['param_name']: p.get('value', p.get('default')) for p in row.module_config or []}
    values['api_token'] = decrypt_secret(values.get('api_token'))
    return Config.from_values(values)


def prepare_parameter(name, value, existing=None):
    if name == 'api_token':
        if value in (None, '', '********') and existing:
            return existing
        if not isinstance(value, str) or not value.strip() or '\r' in value or '\n' in value:
            raise BusinessProcessingError('API token is required')
        return encrypt_secret(value.strip())
    try:
        if name in ('customer_id', 'interval', 'lookback_hours', 'timeout', 'severity_id', 'status_id'):
            maximum = {'interval': 86400, 'lookback_hours': 8760, 'timeout': 600}.get(name, 2147483647)
            return str(positive_int(value, name, maximum))
        if name in ('siem_url', 'verify_tls'):
            config = Config.from_values({'siem_url': 'https://placeholder.invalid', 'api_token': 'placeholder', name: value})
            return config.url if name == 'siem_url' else config.verify_tls
    except ValueError as exc:
        raise BusinessProcessingError(str(exc)) from None
    return value


def public_config(parameters):
    result = copy.deepcopy(parameters or [])
    for parameter in result:
        if parameter['param_name'] == 'api_token':
            parameter['has_value'] = bool(parameter.get('value'))
            parameter['value'] = ''
    return result


class IrisStore:
    def __init__(self, module_id, config):
        self.module_id = module_id
        self.config = config

    def active(self):
        db.session.expire_all()
        row = db.session.get(IrisModule, self.module_id)
        return bool(row and row.is_active and row.module_name == MODULE and configuration(row) == self.config)

    def seen(self, incident_id):
        return db.session.get(MaxPatrolReceipt, (self.config.source_key, incident_id)) is not None

    def create(self, incident_id, payload):
        from app.business.alerts import alerts_create
        from app.models.alerts import Alert
        if not self.active():
            raise ValueError('MaxPatrol module disabled or settings changed')
        alert_uuid = uuid5(NAMESPACE, self.config.source_key + ':' + incident_id)
        alert = Alert(alert_uuid=alert_uuid, **payload)
        # alerts_create's first commit persists both rows. Post-commit hook failures
        # cannot cause duplicate delivery; a pre-commit failure rolls back both.
        db.session.add(MaxPatrolReceipt(source_key=self.config.source_key, incident_id=incident_id,
                                       alert_uuid=alert_uuid,
                                       imported_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        alerts_create(alert, iocs=[], assets=[])

    def rollback(self):
        db.session.rollback()
