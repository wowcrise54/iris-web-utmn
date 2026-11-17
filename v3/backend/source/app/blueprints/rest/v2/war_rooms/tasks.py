#  IRIS Source Code
#  Copyright (C) 2026 - DFIR-IRIS
#  contact@dfir-iris.org

"""War-room tasks REST routes."""

from datetime import datetime

from pydantic import ValidationError

from app.blueprints.access_controls import ac_api_requires
from app.blueprints.access_controls import ac_api_return_access_denied
from app.blueprints.access_controls import ac_fast_check_current_user_has_case_access
from app.blueprints.iris_user import iris_current_user
from app.blueprints.rest.api_doc import api_doc
from app.blueprints.rest.endpoints import response_api_created
from app.blueprints.rest.endpoints import response_api_deleted
from app.blueprints.rest.endpoints import response_api_error
from app.blueprints.rest.endpoints import response_api_not_found
from app.blueprints.rest.endpoints import response_api_success
from app.blueprints.rest.v2.war_rooms.access import can_write_war_room
from app.blueprints.rest.v2.war_rooms.access import require_war_room_read
from app.blueprints.rest.v2.war_rooms.access import require_war_room_write
from app.business.war_room_chat import emit_system_event
from app.business.war_room_task_fan_out import FanOutRequest, InvalidFanOut
from app.business.war_room_tasks import (
    war_room_task_close,
    war_room_task_create,
    war_room_task_delete,
    war_room_task_list,
    war_room_task_reopen,
    war_room_task_update,
    war_room_task_used_tags,
)
from app.datamgmt.war_room_task_fan_out_db import attached_cases, fan_out_task, get_source_task, list_fan_out
from app.db import db
from app.models.authorization import CaseAccessLevel
from app.models.errors import BusinessProcessingError
from app.models.errors import ObjectNotFoundError
from app.web import Blueprint, request


war_rooms_tasks_blueprint = Blueprint(
    'war_rooms_tasks_rest_v2', __name__, url_prefix='/<int:war_room_id>/tasks'
)


@war_rooms_tasks_blueprint.get('/<int:task_id>/fan-out')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='List accessible case tasks linked to this War Room task')
def get_task_fan_out(war_room_id, task_id):
    error = require_war_room_read(war_room_id)
    if error is not None:
        return error
    task = get_source_task(war_room_id, task_id) if 0 < task_id <= 2**63 - 1 else None
    if task is None:
        return response_api_not_found()
    room_write = can_write_war_room(war_room_id)
    case_access = {}
    visible_cases = []
    for case in attached_cases(war_room_id):
        level = ac_fast_check_current_user_has_case_access(
            case.case_id, [CaseAccessLevel.read_only, CaseAccessLevel.full_access],
        )
        if level is not None:
            visible_cases.append(case)
            case_access[case.case_id] = room_write and bool(level & CaseAccessLevel.full_access.value)
    return response_api_success([
        {**row, 'can_create': case_access[row['case_id']]}
        for row in list_fan_out(task, visible_cases)
    ])


@war_rooms_tasks_blueprint.post('/<int:task_id>/fan-out')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='Distribute a task to attached cases')
def post_task_fan_out(war_room_id, task_id):
    error = require_war_room_write(war_room_id)
    if error is not None:
        return error
    if not 0 < task_id <= 2**63 - 1:
        return response_api_not_found()
    try:
        payload = FanOutRequest.model_validate(request.get_json())
    except ValidationError:
        return response_api_error('Invalid task distribution')
    for case_id in payload.case_ids:
        if ac_fast_check_current_user_has_case_access(case_id, [CaseAccessLevel.full_access]) is None:
            return ac_api_return_access_denied(caseid=case_id)
    try:
        result = fan_out_task(war_room_id, task_id, payload, iris_current_user.id)
    except InvalidFanOut as exc:
        db.session.rollback()
        return response_api_error(str(exc))
    return response_api_not_found() if result is None else response_api_success(result)


def _parse_due(raw):
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        raise BusinessProcessingError('due_at must be an ISO date string')
    try:
        # Accept both "YYYY-MM-DD" and full ISO.
        if len(raw) == 10:
            return datetime.fromisoformat(raw)
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        raise BusinessProcessingError('due_at must be an ISO date string')


def _parse_int_list(raw):
    """Parse a repeatable query-string int param into a list.

    Accepts `?status_id=1&status_id=2` or `?status_id=1,2`. Silently
    drops non-integer entries so a bad tag doesn't 400 the whole list
    call.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = raw
    else:
        parts = [p for p in str(raw).split(',') if p]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except (TypeError, ValueError):
            continue
    return out


def _parse_str_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = raw
    else:
        parts = str(raw).split(',')
    return [p.strip() for p in parts if p and p.strip()]


def _serialize_row(row):
    return {
        'task_id': row.task_id,
        'war_room_id': row.war_room_id,
        'title': row.title,
        'description': row.description,
        'status_id': row.status_id,
        'status_name': getattr(row, 'status_name', None),
        'status_bscolor': getattr(row, 'status_bscolor', None),
        'assignee_id': row.assignee_id,
        'assignee_login': row.assignee_login,
        'assignee_name': row.assignee_name,
        'due_at': row.due_at.isoformat() if row.due_at else None,
        'source_case_id': row.source_case_id,
        'source_case_task_id': row.source_case_task_id,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'created_by_id': row.created_by_id,
        # Display names for each actor on the task. Joined server-side
        # so the SPA renders the row in one shot.
        'created_by_login': getattr(row, 'created_by_login', None),
        'created_by_name': getattr(row, 'created_by_name', None),
        'closed_at': row.closed_at.isoformat() if row.closed_at else None,
        'closed_by_id': row.closed_by_id,
        'closed_by_login': getattr(row, 'closed_by_login', None),
        'closed_by_name': getattr(row, 'closed_by_name', None),
        'tags': row.tags,
        'parent_task_id': getattr(row, 'parent_task_id', None),
    }


def _serialize_obj(task):
    """Serialize a plain `WarRoomTask` row (no join info).

    Used by the mutation endpoints. Status name / actor logins are
    resolved via a light relationship lookup so the SPA doesn't have
    to re-request the row after every write.
    """
    status_name = task.status.status_name if task.status else None
    status_bscolor = task.status.status_bscolor if task.status else None
    assignee = task.assignee
    creator = task.created_by
    closer = task.closed_by
    return {
        'task_id': task.task_id,
        'war_room_id': task.war_room_id,
        'title': task.title,
        'description': task.description,
        'status_id': task.status_id,
        'status_name': status_name,
        'status_bscolor': status_bscolor,
        'assignee_id': task.assignee_id,
        'assignee_login': assignee.user if assignee else None,
        'assignee_name': assignee.name if assignee else None,
        'due_at': task.due_at.isoformat() if task.due_at else None,
        'source_case_id': task.source_case_id,
        'source_case_task_id': task.source_case_task_id,
        'created_at': task.created_at.isoformat() if task.created_at else None,
        'created_by_id': task.created_by_id,
        'created_by_login': creator.user if creator else None,
        'created_by_name': creator.name if creator else None,
        'closed_at': task.closed_at.isoformat() if task.closed_at else None,
        'closed_by_id': task.closed_by_id,
        'closed_by_login': closer.user if closer else None,
        'closed_by_name': closer.name if closer else None,
        'tags': task.tags,
        'parent_task_id': getattr(task, 'parent_task_id', None),
    }


def _parse_bool(raw, default=True):
    if raw is None:
        return default
    return str(raw).strip().lower() not in ('0', 'false', 'no', 'off')


def _parse_date_arg(raw):
    """Parse an ISO date/datetime string; returns None if empty/invalid.

    Kept lenient — a bad value silently drops the endpoint rather
    than 400-ing the whole list. That matches the tolerance of the
    other filter parsers on this endpoint.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if len(s) == 10:
            return datetime.fromisoformat(s)
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None


@war_rooms_tasks_blueprint.get('')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='List war room tasks')
def list_tasks(war_room_id):
    err = require_war_room_read(war_room_id)
    if err is not None:
        return err
    q = request.args.get('q') or None
    status_ids = _parse_int_list(request.args.getlist('status_id')
                                  or request.args.get('status_id'))
    assignee_ids_raw = (request.args.getlist('assignee_id')
                        or request.args.get('assignee_id'))
    # Accept `0` to mean Unassigned; parse ints then reinject the flag.
    assignee_ids = []
    if assignee_ids_raw:
        if isinstance(assignee_ids_raw, list):
            parts = assignee_ids_raw
        else:
            parts = str(assignee_ids_raw).split(',')
        for p in parts:
            p = str(p).strip().lower()
            if p in ('0', 'unassigned', 'null', 'none'):
                assignee_ids.append(0)
                continue
            try:
                assignee_ids.append(int(p))
            except ValueError:
                continue
    tags = _parse_str_list(request.args.getlist('tag')
                            or request.args.get('tag'))
    parent = request.args.get('parent_task_id')
    if parent is None:
        parent_task_id = -1
    else:
        p = str(parent).strip().lower()
        if p in ('', 'null', 'none', 'top', 'root'):
            parent_task_id = 0
        else:
            try:
                parent_task_id = int(p)
            except ValueError:
                parent_task_id = -1
    include_closed = _parse_bool(request.args.get('include_closed'), True)
    due_from = _parse_date_arg(request.args.get('due_from'))
    due_to = _parse_date_arg(request.args.get('due_to'))
    include_no_due = _parse_bool(request.args.get('include_no_due'), True)

    # Pagination is opt-in: `page` present → return the envelope;
    # absent → return the raw array (back-compat with earlier callers).
    page_raw = request.args.get('page')
    if page_raw is None:
        rows = war_room_task_list(
            war_room_id,
            q=q,
            status_ids=status_ids or None,
            tags=tags or None,
            assignee_ids=assignee_ids or None,
            parent_task_id=parent_task_id,
            due_from=due_from,
            due_to=due_to,
            include_no_due=include_no_due,
            include_closed=include_closed,
        )
        return response_api_success(data=[_serialize_row(r) for r in rows])

    try:
        page = int(page_raw)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get('per_page', 25))
    except (TypeError, ValueError):
        per_page = 25
    envelope = war_room_task_list(
        war_room_id,
        q=q,
        status_ids=status_ids or None,
        tags=tags or None,
        assignee_ids=assignee_ids or None,
        parent_task_id=parent_task_id,
        due_from=due_from,
        due_to=due_to,
        include_no_due=include_no_due,
        include_closed=include_closed,
        page=page,
        per_page=per_page,
    )
    envelope['data'] = [_serialize_row(r) for r in envelope['data']]
    return response_api_success(data=envelope)


@war_rooms_tasks_blueprint.get('/tags')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='List tags used on war room tasks')
def list_used_tags(war_room_id):
    """Distinct tag values already in use in this war room."""
    err = require_war_room_read(war_room_id)
    if err is not None:
        return err
    return response_api_success(data=war_room_task_used_tags(war_room_id))


@war_rooms_tasks_blueprint.post('')
@ac_api_requires()
@api_doc(response_shape='created', tags=['WarRoomTasks'], summary='Create a war room task')
def create_task(war_room_id):
    err = require_war_room_write(war_room_id)
    if err is not None:
        return err
    raw = request.get_json()
    if not isinstance(raw, dict):
        return response_api_error('Invalid request')
    try:
        due_at = _parse_due(raw.get('due_at'))
        task = war_room_task_create(
            war_room_id,
            title=raw.get('title'),
            description=raw.get('description'),
            status_id=raw.get('status_id'),
            assignee_id=raw.get('assignee_id'),
            due_at=due_at,
            source_case_id=raw.get('source_case_id'),
            source_case_task_id=raw.get('source_case_task_id'),
            tags=raw.get('tags'),
            parent_task_id=raw.get('parent_task_id'),
            created_by_id=iris_current_user.id,
        )
    except BusinessProcessingError as e:
        return response_api_error(e.get_message())
    emit_system_event(
        war_room_id, 'task_assigned',
        f'Created task: {task.title}',
        author_id=iris_current_user.id,
        ref_type='war_room_task', ref_id=task.task_id,
    )
    return response_api_created(_serialize_obj(task))


@war_rooms_tasks_blueprint.patch('/<int:task_id>')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='Update a war room task')
def update_task(war_room_id, task_id):
    err = require_war_room_write(war_room_id)
    if err is not None:
        return err
    raw = request.get_json()
    if not isinstance(raw, dict):
        return response_api_error('Invalid request')
    try:
        fields = {k: raw[k] for k in raw if k in
                  ('title', 'description', 'status_id', 'assignee_id',
                   'source_case_id', 'source_case_task_id', 'tags',
                   'parent_task_id')}
        if 'due_at' in raw:
            fields['due_at'] = _parse_due(raw['due_at'])
        fields['updated_by_id'] = iris_current_user.id
        task = war_room_task_update(war_room_id, task_id, **fields)
    except ObjectNotFoundError:
        return response_api_not_found()
    except BusinessProcessingError as e:
        return response_api_error(e.get_message())
    return response_api_success(_serialize_obj(task))


@war_rooms_tasks_blueprint.post('/<int:task_id>/close')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='Close a war room task')
def close_task(war_room_id, task_id):
    err = require_war_room_write(war_room_id)
    if err is not None:
        return err
    try:
        task = war_room_task_close(war_room_id, task_id,
                                    closed_by_id=iris_current_user.id)
    except ObjectNotFoundError:
        return response_api_not_found()
    emit_system_event(
        war_room_id, 'task_completed',
        f'Closed task: {task.title}',
        author_id=iris_current_user.id,
        ref_type='war_room_task', ref_id=task.task_id,
    )
    return response_api_success(_serialize_obj(task))


@war_rooms_tasks_blueprint.post('/<int:task_id>/reopen')
@ac_api_requires()
@api_doc(tags=['WarRoomTasks'], summary='Reopen a war room task')
def reopen_task(war_room_id, task_id):
    err = require_war_room_write(war_room_id)
    if err is not None:
        return err
    try:
        task = war_room_task_reopen(war_room_id, task_id)
    except ObjectNotFoundError:
        return response_api_not_found()
    emit_system_event(
        war_room_id, 'task_assigned',
        f'Reopened task: {task.title}',
        author_id=iris_current_user.id,
        ref_type='war_room_task', ref_id=task.task_id,
    )
    return response_api_success(_serialize_obj(task))


@war_rooms_tasks_blueprint.delete('/<int:task_id>')
@ac_api_requires()
@api_doc(response_shape='deleted', tags=['WarRoomTasks'], summary='Delete a war room task')
def delete_task(war_room_id, task_id):
    err = require_war_room_write(war_room_id)
    if err is not None:
        return err
    try:
        war_room_task_delete(war_room_id, task_id)
    except ObjectNotFoundError:
        return response_api_not_found()
    return response_api_deleted()
