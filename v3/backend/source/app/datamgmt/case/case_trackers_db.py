from sqlalchemy.orm.exc import StaleDataError

from app.business.case_trackers import prepare_tracker_rows
from app.datamgmt.case.case_tracker_items_db import validate_new_tracker_items
from app.datamgmt.case.case_tracker_timeline_db import append_tracker_events
from app.db import db
from app.models.case_trackers import CaseTracker


def list_trackers(case_id):
    query = CaseTracker.query.filter_by(case_id=case_id).order_by(CaseTracker.id)
    return [serialize_tracker(tracker) for tracker in query]


def serialize_tracker(tracker):
    return {'id': tracker.id, 'version': tracker.version, **tracker.data}


def save_tracker(case_id, tracker_id, version, data, user_id=None):
    changes = []
    if tracker_id is None:
        validate_new_tracker_items(case_id, data, {'rows': []})
        changes = prepare_tracker_rows(data, None)
        tracker = CaseTracker(case_id=case_id, data=data)
        db.session.add(tracker)
    else:
        tracker = CaseTracker.query.filter_by(case_id=case_id, id=tracker_id).one_or_none()
        if tracker is None:
            return None
        if tracker.version != version:
            raise StaleDataError()
        if data is None:
            db.session.delete(tracker)
        else:
            validate_new_tracker_items(case_id, data, tracker.data)
            changes = prepare_tracker_rows(data, tracker.data)
            tracker.data = data
    db.session.flush()
    if changes:
        append_tracker_events(case_id, tracker.id, data['name'], user_id, changes)
    result = {} if data is None else serialize_tracker(tracker)
    db.session.commit()
    return result
