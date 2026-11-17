from collections import defaultdict

from sqlalchemy import select

from app.db import db
from app.models.assets import CaseAssets
from app.models.evidences import CaseReceivedFile
from app.models.iocs import Ioc
from app.models.models import CaseTasks


ITEMS = {
    'asset': (CaseAssets.asset_id, CaseAssets.case_id, CaseAssets.asset_name),
    'ioc': (Ioc.ioc_id, Ioc.case_id, Ioc.ioc_value),
    'task': (CaseTasks.id, CaseTasks.task_case_id, CaseTasks.task_title),
    'evidence': (CaseReceivedFile.id, CaseReceivedFile.case_id, CaseReceivedFile.filename),
}


class InvalidTrackerItem(ValueError):
    pass


def list_tracker_items(case_id, kind, search, after):
    identifier, owner, label = ITEMS[kind]
    query = select(identifier, label).where(owner == case_id, identifier > after)
    if search:
        query = query.where(label.icontains(search, autoescape=True))
    rows = db.session.execute(query.order_by(identifier).limit(51)).all()
    return {
        'items': [
            {'kind': kind, 'id': item_id, 'label': (name or f'#{item_id}')[:128]}
            for item_id, name in rows[:50]
        ],
        'next_after': rows[49][0] if len(rows) > 50 else None,
    }


def _references(data):
    return {
        (row['item']['kind'], row['item']['id'])
        for row in data['rows']
        if row.get('item') is not None
    }


def validate_new_tracker_items(case_id, data, previous):
    # Keep an existing row editable after its case item was deleted.
    added = defaultdict(set)
    for kind, item_id in _references(data) - _references(previous):
        added[kind].add(item_id)
    for kind, ids in added.items():
        identifier, owner, _ = ITEMS[kind]
        found = db.session.scalars(select(identifier).where(owner == case_id, identifier.in_(ids)))
        if set(found) != ids:
            raise InvalidTrackerItem('A linked item is unavailable in this case.')
