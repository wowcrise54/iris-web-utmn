from datetime import UTC, datetime

from sqlalchemy import select

from app.datamgmt.case.case_tracker_items_db import ITEMS
from app.datamgmt.states import update_timeline_state
from app.db import db
from app.models.cases import CaseEventTimeline, CaseTimeline, CasesEvent
from app.models.models import CaseEventsAssets, CaseEventsIoc


_LINK_MODELS = {
    'asset': (CaseEventsAssets, 'asset_id'),
    'ioc': (CaseEventsIoc, 'ioc_id'),
}


def _owned_links(case_id, changes):
    owned = {}
    for kind in _LINK_MODELS:
        ids = {
            row['item']['id'] for row, _, _ in changes
            if row.get('item') and row['item']['kind'] == kind
        }
        if ids:
            identifier, owner, _ = ITEMS[kind]
            owned[kind] = set(db.session.scalars(
                select(identifier).where(owner == case_id, identifier.in_(ids)).with_for_update(read=True)
            ))
    return owned


def append_tracker_events(case_id, tracker_id, tracker_name, user_id, changes):
    if not changes:
        return
    timeline_id = db.session.scalar(select(CaseTimeline.timeline_id).where(
        CaseTimeline.case_id == case_id, CaseTimeline.is_default.is_(True),
    ))
    owned = _owned_links(case_id, changes)
    now = datetime.now(UTC).replace(tzinfo=None)
    events = []
    for row, step, completed in changes:
        status = 'completed' if completed else 'reopened'
        event = CasesEvent(
            case_id=case_id, user_id=user_id, event_source='Response tracker',
            event_title=f"{tracker_name} · {row['label']} · {step} ({status})",
            event_date=now, event_date_wtz=now, event_added=now, event_tz='+00:00',
            custom_attributes={'response_tracker': {
                'tracker_id': tracker_id, 'row_id': row['id'], 'step': step,
                'completed': completed, 'item': row.get('item'),
            }},
        )
        db.session.add(event)
        events.append((event, row.get('item')))
    db.session.flush()
    for event, item in events:
        if timeline_id is not None:
            db.session.add(CaseEventTimeline(event_id=event.event_id, timeline_id=timeline_id))
        if item and item['id'] in owned.get(item['kind'], ()):
            model, column = _LINK_MODELS[item['kind']]
            db.session.add(model(event_id=event.event_id, case_id=case_id, **{column: item['id']}))
    update_timeline_state(case_id, user_id)
