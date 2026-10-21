"""Native module settings and transactional incident ingestion."""
import copy
from datetime import datetime, timezone
from uuid import UUID, uuid5

from app.db import db
from app.models.errors import BusinessProcessingError
from app.models.models import IrisModule
from app.models.maxpatrol import MaxPatrolReceipt
from app.iris_engine.mail.secrets import encrypt_secret, decrypt_secret
from iris_maxpatrol_module.collector import Config, positive_int, event_uuid, render_event_tree

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

    def _imported_alert(self, incident_id):
        from app.models.alerts import Alert
        receipt = db.session.get(MaxPatrolReceipt, (self.config.source_key, incident_id))
        if not receipt:
            return None
        return db.session.query(Alert).filter_by(alert_uuid=receipt.alert_uuid, alert_customer_id=self.config.customer_id,
                                     alert_source='MaxPatrol SIEM', alert_source_ref=incident_id).first()

    def needs_event_refresh(self, incident_id):
        alert = self._imported_alert(incident_id)
        if not alert:
            return False
        return self._event_refresh_due(alert)

    def stored_incident(self, incident_id):
        alert = self._imported_alert(incident_id)
        content = alert.alert_source_content if alert and isinstance(alert.alert_source_content, dict) else {}
        incident = content.get('incident')
        if isinstance(incident, dict) and incident.get('id') == incident_id:
            return copy.deepcopy(incident)
        return None

    def refresh_candidates(self):
        from app.models.alerts import Alert
        rows = db.session.query(MaxPatrolReceipt, Alert).join(Alert,
            Alert.alert_uuid == MaxPatrolReceipt.alert_uuid).filter(
                MaxPatrolReceipt.source_key == self.config.source_key,
                Alert.alert_customer_id == self.config.customer_id,
                Alert.alert_source == 'MaxPatrol SIEM',
                Alert.alert_source_ref == MaxPatrolReceipt.incident_id).all()
        return [receipt.incident_id for receipt, alert in rows if self._event_refresh_due(alert)]

    def _event_refresh_due(self, alert):
        content = alert.alert_source_content if isinstance(alert.alert_source_content, dict) else {}
        state = content.get('event_collection')
        if not isinstance(state, dict):
            return True
        if state.get('version') != 2 or not state.get('complete'):
            return True
        try:
            collected = datetime.fromisoformat(state['collected_at'].replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - collected).total_seconds() >= max(300, self.config.interval)
        except (KeyError, ValueError, TypeError, AttributeError):
            return True

    def refresh_events(self, incident_id, materials):
        if not self.active():
            raise ValueError('MaxPatrol module disabled or settings changed')
        alert = self._imported_alert(incident_id)
        if not alert:
            return False
        content = copy.deepcopy(alert.alert_source_content) if isinstance(alert.alert_source_content, dict) else {}
        # Retain earlier evidence if a later attempt returns only a partial graph.
        events, unidentified = {}, []
        for row in [*(content.get('events') or []), *(materials.get('events') or [])]:
            uid = event_uuid(row)
            if uid:
                events[uid] = {**events.get(uid, {}), **row}
            elif row not in unidentified:
                unidentified.append(row)
        old_roots = [node.get('uuid') for node in content.get('event_tree') or []]
        links = copy.deepcopy(content.get('event_links') or {})
        if not (materials.get('event_collection') or {}).get('complete'):
            for uid, children in (materials.get('event_links') or {}).items():
                links[uid] = list(dict.fromkeys([*links.get(uid, []), *children]))
            roots = [*old_roots, *(node.get('uuid') for node in materials.get('event_tree') or [])]
        else:
            links = materials.get('event_links') or links
            roots = [node.get('uuid') for node in materials.get('event_tree') or []]
        content.update(materials)
        content['events'] = [*events.values(), *unidentified]
        content['event_links'] = links
        content['event_tree'] = render_event_tree(roots, events, links)
        alert.alert_source_content = content
        db.session.commit()
        return True

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
