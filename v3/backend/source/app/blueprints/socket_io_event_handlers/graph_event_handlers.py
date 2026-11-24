"""Case-scoped graph updates and viewer presence."""

import logging
from uuid import uuid4

from app import socket_io
from app.blueprints.access_controls import is_user_authenticated
from app.blueprints.iris_user import iris_current_user
from app.business.access_controls import ac_fast_check_user_has_case_access
from app.business.auth import auth_session_is_live, validate_auth_token
from app.models.authorization import CaseAccessLevel
from app.socket_transport import join_room, leave_room
from app.web import request


NAMESPACE = '/case-graph'
_READ_LEVELS = [CaseAccessLevel.read_only, CaseAccessLevel.full_access]
_members = {}
log = logging.getLogger(__name__)


def _room(case_id):
    return f'case-graph:{case_id}'


def _publish(case_id, event, payload):
    try:
        socket_io.emit(event, payload, to=_room(case_id), namespace=NAMESPACE)
    except Exception:
        log.exception('Failed to publish graph socket event %s for case %s', event, case_id)


def publish_graph_change(case_id, actor):
    _publish(case_id, 'graph-changed', {'updated_by': actor})


@socket_io.on('connect', namespace=NAMESPACE)
def connect(credentials):
    if not isinstance(credentials, dict):
        return False
    case_id = credentials.get('case_id')
    if type(case_id) is not int or not 0 < case_id <= 2**31 - 1:
        return False

    user_id = None
    name = None
    session_id = None
    if is_user_authenticated(request):
        user_id = iris_current_user.id
        name = iris_current_user.name or iris_current_user.user
    elif isinstance(credentials.get('token'), str):
        data = validate_auth_token(credentials['token'])
        if data and not (data.get('mfa_required') and not data.get('mfa_verified')):
            user_id = data.get('user_id')
            name = data.get('user_name') or data.get('user_login')
            session_id = data.get('session_id')

    if not user_id or not ac_fast_check_user_has_case_access(user_id, case_id, _READ_LEVELS):
        return False
    join_room(_room(case_id))
    _members[request.sid] = (case_id, {
        'peer': uuid4().hex, 'user_id': user_id, 'name': name or str(user_id),
    }, session_id)
    return True


@socket_io.on('graph-heartbeat', namespace=NAMESPACE)
def heartbeat():
    member = _members.get(request.sid)
    if member is None:
        return
    case_id, viewer, session_id = member
    if ((session_id is not None and not auth_session_is_live(session_id))
            or not ac_fast_check_user_has_case_access(viewer['user_id'], case_id, _READ_LEVELS)):
        leave_room(_room(case_id))
        disconnect()
        return
    _publish(case_id, 'graph-viewer', viewer)


@socket_io.on('disconnect', namespace=NAMESPACE)
def disconnect():
    member = _members.pop(request.sid, None)
    if member is not None:
        case_id, viewer, _ = member
        _publish(case_id, 'graph-viewer-left', {'peer': viewer['peer']})
