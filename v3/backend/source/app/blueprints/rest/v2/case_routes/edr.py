"""Case-scoped discovery and confirmed execution of MaxPatrol EDR actions."""
from contextlib import closing
from dataclasses import asdict
from hashlib import sha256
import json
import logging
from uuid import uuid4

from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import text

from app.blueprints.access_controls import ac_api_requires, ac_api_return_access_denied
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.endpoints import response_api_error, response_api_success
from app.blueprints.rest.v2.case_routes.sandbox import access
from app.business.maxpatrol import MODULE, configuration
from app.db import db
from app.iris_engine.utils.tracker import track_activity
from app.models.alerts import Alert, AlertCaseAssociation
from app.models.maxpatrol import MaxPatrolReceipt
from app.models.models import IrisModule, UserActivity
from app.web import Blueprint, current_app, request
from iris_maxpatrol_module.collector import SIEMError
from iris_maxpatrol_module.edr import EdrClient, eligible_events, execution_enabled, summarize_events


case_edr_blueprint = Blueprint('case_edr', __name__, url_prefix='/<int:case_identifier>/edr')
log = logging.getLogger('iris.edr')


def sources(case_id, config, alert_id=None):
    query = db.session.query(Alert.alert_id, Alert.alert_title, Alert.alert_source_content['events']).join(
        AlertCaseAssociation, AlertCaseAssociation.alert_id == Alert.alert_id,
    ).join(MaxPatrolReceipt, MaxPatrolReceipt.alert_uuid == Alert.alert_uuid).filter(
        AlertCaseAssociation.case_id == case_id,
        MaxPatrolReceipt.source_key == config.source_key,
        MaxPatrolReceipt.incident_id == Alert.alert_source_ref,
        Alert.alert_customer_id == config.customer_id,
        Alert.alert_source == 'MaxPatrol SIEM',
    )
    if alert_id is not None:
        query = query.filter(Alert.alert_id == alert_id)
    return query.order_by(Alert.alert_id.desc()).yield_per(10)


def active_module():
    return db.session.query(IrisModule).filter_by(module_name=MODULE, is_active=True).first()


def serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='case-edr-response')


def fingerprint(target, config):
    return sha256(json.dumps([config.source_key, asdict(target)], sort_keys=True).encode()).hexdigest()


@case_edr_blueprint.get('')
@ac_api_requires()
def list_events(case_identifier):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    row = active_module()
    try:
        config = configuration(row) if row else None
    except ValueError:
        return response_api_error('MaxPatrol SIEM configuration is invalid')
    linked_alerts = db.session.query(AlertCaseAssociation).filter_by(case_id=case_identifier).count()
    events, counts = summarize_events(sources(case_identifier, config) if config else ())
    log.info('EDR case=%s module_active=%s linked_alerts=%s matched_alerts=%s saved_events=%s eligible_events=%s',
             case_identifier, config is not None, linked_alerts, counts['matched_alerts'],
             counts['saved_events'], len(events))
    return response_api_success({
        'events': events, 'execution_enabled': row is not None and execution_enabled(row.module_config),
        'module_active': config is not None, 'linked_alerts': linked_alerts, **counts,
    })


def candidate(case_id, alert_id, uid):
    row = active_module()
    if row is None:
        raise ValueError('MaxPatrol SIEM module is disabled')
    config = configuration(row)
    matches = [
        event for _, _, saved in sources(case_id, config, alert_id)
        for event_id, event in eligible_events(saved) if event_id == uid
    ]
    if len(matches) != 1:
        raise ValueError('The event is unavailable or ambiguous in this case')
    return config, matches[0]


@case_edr_blueprint.get('/<int:alert_id>/<string:event_id>')
@ac_api_requires()
def preview(case_identifier, alert_id, event_id):
    if not access(case_identifier):
        return ac_api_return_access_denied()
    try:
        config, event = candidate(case_identifier, alert_id, event_id)
        with closing(EdrClient(config)) as client:
            targets = client.discover(event)
    except SIEMError as exc:
        return response_api_error(f'MaxPatrol discovery failed ({exc.code})')
    except ValueError as exc:
        return response_api_error(str(exc))
    return response_api_success({'actions': [
        {
            'module': target.module, 'action': target.action, 'title': target.title,
            'agent': target.agent, 'hostname': target.hostname, 'parameters': target.parameters,
            'confirmation': serializer().dumps([
                case_identifier, iris_current_user.id, alert_id, event_id,
                fingerprint(target, config), uuid4().hex,
            ]),
        }
        for target in targets
    ]})


@case_edr_blueprint.post('')
@ac_api_requires()
def execute(case_identifier):
    if not access(case_identifier, True):
        return ac_api_return_access_denied()
    row = active_module()
    if row is None or not execution_enabled(row.module_config):
        return response_api_error('EDR action execution is disabled')
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get('confirmed') is not True:
        return response_api_error('Confirm the EDR action before execution')
    token = payload.get('confirmation')
    try:
        if not isinstance(token, str) or len(token) > 2048:
            raise BadData('Invalid confirmation')
        case_id, user_id, alert_id, uid, expected, nonce = serializer().loads(token, max_age=300)
    except BadData:
        return response_api_error('The confirmation has expired or is invalid')
    if case_id != case_identifier or user_id != iris_current_user.id:
        return ac_api_return_access_denied()
    try:
        config, event = candidate(case_id, alert_id, uid)
        with closing(EdrClient(config)) as client:
            target = next((item for item in client.discover(event) if fingerprint(item, config) == expected), None)
            if target is None:
                return response_api_error('The EDR target or available action changed. Review it again.')
            attempt = (f'EDR {target.module}/{target.action} requested for alert #{alert_id}, '
                       f'event {uid}, agent {target.agent} ({nonce})')
            # Serialize claims of the same confirmation across web workers.
            lock = int.from_bytes(bytes.fromhex(nonce)[:8], 'big', signed=True)
            db.session.execute(text('SELECT pg_advisory_xact_lock(:lock)'), {'lock': lock})
            claimed = db.session.query(UserActivity).filter_by(case_id=case_id, activity_desc=attempt.capitalize()).first()
            if claimed is not None:
                return response_api_error('This confirmation was already used. Check the case activity.')
            activity = track_activity(attempt, caseid=case_id)
            try:
                result = client.execute(target)
            except SIEMError as exc:
                result = {'status': 'unknown', 'reason': exc.code}
            track_activity(
                f'EDR action result for activity #{activity.id}: {result["status"]}',
                caseid=case_id,
            )
            return response_api_success(result)
    except SIEMError as exc:
        return response_api_error(f'MaxPatrol discovery failed ({exc.code})')
    except ValueError as exc:
        return response_api_error(str(exc))
