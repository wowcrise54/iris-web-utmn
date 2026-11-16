"""Wazuh configuration and atomic alert receipts."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid5

from app.db import db
from app.models.errors import BusinessProcessingError
from app.models.models import IrisModule
from app.models.wazuh import WazuhReceipt
from app.iris_engine.mail.secrets import decrypt_secret, encrypt_secret
from iris_wazuh_module.collector import Client, make_alert

MODULE = 'iris_wazuh_module'
NAMESPACE = UUID('90c63d94-406d-40f1-83f9-fc7401e88636')


def prepare_parameter(name, value, existing=None):
    if name == 'password':
        if value in (None, '', '********') and existing:
            return existing
        if not isinstance(value, str) or not value or '\n' in value or '\r' in value:
            raise BusinessProcessingError('Indexer password is required')
        return encrypt_secret(value)
    if name == 'verify_tls':
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        raise BusinessProcessingError('TLS verification must be true or false')
    if name in ('customer_id', 'severity_id', 'status_id', 'interval', 'timeout', 'min_level'):
        try:
            number = int(value)
            maximum = {'interval': 86400, 'timeout': 600, 'min_level': 15}.get(name, 2147483647)
            if isinstance(value, bool) or not 1 <= number <= maximum:
                raise ValueError()
            return str(number)
        except (TypeError, ValueError):
            raise BusinessProcessingError('Invalid value for ' + name) from None
    return value


def public_config(parameters):
    result = copy.deepcopy(parameters or [])
    for parameter in result:
        if parameter.get('param_name') == 'password':
            parameter['has_value'] = bool(parameter.get('value'))
            parameter['value'] = ''
    return result


def configuration(row):
    values = {p['param_name']: p.get('value', p.get('default')) for p in row.module_config or []}
    values['password'] = decrypt_secret(values.get('password'))
    for name in ('customer_id', 'severity_id', 'status_id', 'interval', 'timeout', 'min_level'):
        values[name] = int(prepare_parameter(name, values.get(name)))
    values['verify_tls'] = values.get('verify_tls', True)
    if not isinstance(values['verify_tls'], bool):
        raise ValueError('Invalid TLS verification setting')
    # Validate connection settings without making a request.
    client = Client(values['url'], values['username'], values['password'], values['index'],
                    values['timeout'], values['verify_tls'])
    client.close()
    parts = urlsplit(values['url'])
    normalized_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), '', ''))
    identity = [normalized_url, values['index'], values['customer_id']]
    values['source_key'] = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()
    return values


def initialize(row):
    """Record the first activation boundary before the module becomes active."""
    from app.models.wazuh import WazuhPollState
    config = configuration(row)
    if not db.session.get(WazuhPollState, config['source_key']):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.add(WazuhPollState(source_key=config['source_key'], started_at=now,
                                      watermark=now, last_poll=now))
        db.session.commit()


class IrisStore:
    def __init__(self, module_id, config, state):
        self.module_id, self.config, self.state = module_id, config, state

    def key(self, hit):
        return hashlib.sha256(json.dumps([hit['_index'], hit['_id']], ensure_ascii=True).encode()).hexdigest()

    def seen(self, hit):
        return db.session.get(WazuhReceipt, (self.config['source_key'], self.key(hit))) is not None

    def _ensure_active(self):
        row = (db.session.query(IrisModule).filter_by(id=self.module_id)
               .populate_existing().with_for_update().first())
        if not row or not row.is_active or row.module_name != MODULE or configuration(row) != self.config:
            raise ValueError('Wazuh module disabled or settings changed')

    def create(self, hit):
        from app.business.alerts import alerts_create
        from app.models.alerts import Alert
        self._ensure_active()
        key = self.key(hit)
        alert_uuid = uuid5(NAMESPACE, self.config['source_key'] + ':' + key)
        alert = Alert(alert_uuid=alert_uuid, **make_alert(hit, self.config['customer_id'],
                      self.config['severity_id'], self.config['status_id']))
        db.session.add(WazuhReceipt(source_key=self.config['source_key'], document_key=key, alert_uuid=alert_uuid))
        alerts_create(alert, iocs=[], assets=[])

    def advance(self, end):
        self._ensure_active()
        self.state.watermark = end
        db.session.commit()
