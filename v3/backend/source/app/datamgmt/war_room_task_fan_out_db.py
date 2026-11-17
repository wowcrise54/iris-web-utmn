from sqlalchemy import select

from app.business.war_room_task_fan_out import InvalidFanOut, default_task_status_id, fan_out_tags
from app.datamgmt.case.case_tasks_db import stage_task
from app.db import db
from app.models.authorization import CaseAccessLevel, User, UserCaseEffectiveAccess
from app.models.cases import Cases
from app.models.models import CaseTasks, TaskAssignee, TaskStatus
from app.models.war_room_task_fan_out import WarRoomTaskFanOut
from app.models.war_rooms import WarRoomCase, WarRoomTask


def get_source_task(war_room_id, task_id, *, lock=False):
    query = select(WarRoomTask).where(WarRoomTask.war_room_id == war_room_id, WarRoomTask.task_id == task_id)
    return db.session.scalar(query.with_for_update() if lock else query)


def attached_cases(war_room_id, case_ids=None):
    query = select(Cases.case_id, Cases.name).join(WarRoomCase, WarRoomCase.case_id == Cases.case_id).where(
        WarRoomCase.war_room_id == war_room_id,
    )
    if case_ids is not None:
        query = query.where(Cases.case_id.in_(case_ids))
    return db.session.execute(query.order_by(Cases.case_id)).all()


def task_statuses():
    return db.session.execute(select(TaskStatus.id, TaskStatus.status_name).order_by(TaskStatus.id)).all()


def _existing_tasks(task, case_ids):
    linked = db.session.execute(
        select(WarRoomTaskFanOut.case_id, CaseTasks.id, TaskStatus.status_name)
        .join(CaseTasks, (CaseTasks.id == WarRoomTaskFanOut.case_task_id)
              & (CaseTasks.task_case_id == WarRoomTaskFanOut.case_id))
        .outerjoin(TaskStatus, TaskStatus.id == CaseTasks.task_status_id)
        .where(WarRoomTaskFanOut.war_room_task_id == task.task_id, WarRoomTaskFanOut.case_id.in_(case_ids))
    )
    existing = {case_id: (task_id, status) for case_id, task_id, status in linked}
    if task.source_case_task_id is not None and task.source_case_id in case_ids:
        source = db.session.execute(
            select(CaseTasks.id, TaskStatus.status_name)
            .outerjoin(TaskStatus, TaskStatus.id == CaseTasks.task_status_id)
            .where(CaseTasks.id == task.source_case_task_id, CaseTasks.task_case_id == task.source_case_id)
        ).one_or_none()
        if source is not None:
            existing.setdefault(task.source_case_id, tuple(source))
    return existing


def list_fan_out(task, cases):
    existing = _existing_tasks(task, [case_id for case_id, _ in cases])
    return [
        {'case_id': case_id, 'case_name': name,
         'case_task_id': existing.get(case_id, (None, None))[0],
         'status_name': existing.get(case_id, (None, None))[1]}
        for case_id, name in cases
    ]


def _case_owners(case_ids):
    access = UserCaseEffectiveAccess.access_level
    allowed = CaseAccessLevel.read_only.value | CaseAccessLevel.full_access.value
    rows = db.session.execute(
        select(Cases.case_id, Cases.owner_id)
        .join(User, User.id == Cases.owner_id)
        .join(UserCaseEffectiveAccess, (UserCaseEffectiveAccess.case_id == Cases.case_id)
              & (UserCaseEffectiveAccess.user_id == Cases.owner_id))
        .where(Cases.case_id.in_(case_ids), User.active.is_(True),
               access.bitwise_and(allowed) != 0, access.bitwise_and(CaseAccessLevel.deny_all.value) == 0)
    )
    return dict(rows.tuples().all())


def fan_out_task(war_room_id, task_id, payload, user_id):
    task = get_source_task(war_room_id, task_id, lock=True)
    if task is None:
        return None
    case_ids = payload.case_ids
    attached = set(db.session.scalars(
        select(WarRoomCase.case_id).where(
            WarRoomCase.war_room_id == war_room_id, WarRoomCase.case_id.in_(case_ids),
        ).with_for_update(read=True)
    ))
    if attached != set(case_ids):
        raise InvalidFanOut('Select cases attached to this war room.')

    existing = _existing_tasks(task, case_ids)
    pending = [case_id for case_id in case_ids if case_id not in existing]
    created = {}
    if pending:
        statuses = task_statuses()
        status_id = payload.status_id or default_task_status_id(statuses)
        if status_id not in dict(statuses):
            raise InvalidFanOut('Select an available task status.')
        owners = _case_owners(pending) if payload.assign_to_case_owner else {}
        tags = fan_out_tags(task.tags)
        for case_id in sorted(pending):
            case_task = CaseTasks(
                task_title=task.title, task_description=task.description, task_tags=tags,
                task_status_id=status_id,
            )
            stage_task(case_task, user_id, case_id)
            db.session.flush()
            db.session.add(WarRoomTaskFanOut(
                war_room_task_id=task_id, case_id=case_id, case_task_id=case_task.id,
            ))
            if case_id in owners:
                db.session.add(TaskAssignee(task_id=case_task.id, user_id=owners[case_id]))
            created[case_id] = case_task.id
    result = [
        {'case_id': case_id, 'case_task_id': created[case_id], 'status': 'created'}
        if case_id in created else
        {'case_id': case_id, 'case_task_id': existing[case_id][0], 'status': 'exists'}
        for case_id in case_ids
    ]
    db.session.commit()
    return result
