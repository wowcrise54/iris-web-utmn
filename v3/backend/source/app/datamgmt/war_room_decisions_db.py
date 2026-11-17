from datetime import UTC, datetime

from sqlalchemy import select

from app.business.war_room_decisions import validate_decision_transition
from app.db import db
from app.models.war_room_decisions import WarRoomDecision


def _serialize(row):
    return {
        'id': row.id, 'title': row.title, 'rationale': row.rationale,
        'status': row.status, 'history': row.history,
    }


def _history_entry(status, actor_id, actor_name, comment=''):
    return {
        'status': status, 'actor_id': actor_id, 'actor_name': actor_name,
        'at': datetime.now(UTC).isoformat(), 'comment': comment,
    }


def list_decisions(war_room_id, before):
    query = select(WarRoomDecision).where(WarRoomDecision.war_room_id == war_room_id)
    if before is not None:
        query = query.where(WarRoomDecision.id < before)
    rows = db.session.scalars(query.order_by(WarRoomDecision.id.desc()).limit(51)).all()
    return {
        'items': [_serialize(row) for row in rows[:50]],
        'next_before': rows[49].id if len(rows) > 50 else None,
    }


def create_decision(war_room_id, title, rationale, actor_id, actor_name):
    row = WarRoomDecision(
        war_room_id=war_room_id, title=title, rationale=rationale, status='proposed',
        history=[_history_entry('proposed', actor_id, actor_name)],
    )
    db.session.add(row)
    db.session.flush()
    result = _serialize(row)
    db.session.commit()
    return result


def transition_decision(war_room_id, decision_id, status, actor_id, actor_name, comment):
    row = db.session.scalar(select(WarRoomDecision).where(
        WarRoomDecision.war_room_id == war_room_id, WarRoomDecision.id == decision_id,
    ).with_for_update())
    if row is None:
        return None
    validate_decision_transition(row.status, status)
    row.status = status
    row.history = [*row.history, _history_entry(status, actor_id, actor_name, comment)]
    result = _serialize(row)
    db.session.commit()
    return result
