from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Cell = Annotated[str, StringConstraints(max_length=512)]
ItemKind = Literal['asset', 'ioc', 'task', 'evidence']


class TrackerItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    kind: ItemKind
    id: int = Field(gt=0, le=2**63 - 1)


class TrackerRow(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    label: Label
    id: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{32}$')] | None = None
    values: list[Cell] = Field(max_length=10)
    completed: list[bool] = Field(max_length=20)
    item: TrackerItem | None = None


class TrackerSchema(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    name: Label
    columns: list[Label] = Field(max_length=10)
    steps: list[Label] = Field(min_length=1, max_length=20)
    rows: list[TrackerRow] = Field(max_length=200)
    timeline_sync: bool = False

    @model_validator(mode='after')
    def validate_table(self):
        for labels in (self.columns, self.steps):
            if len({label.casefold() for label in labels}) != len(labels):
                raise ValueError('Column and step names must be unique within their group.')
        for row in self.rows:
            if len(row.values) != len(self.columns) or len(row.completed) != len(self.steps):
                raise ValueError('Row values and completion flags must match the tracker configuration.')
        items = [(row.item.kind, row.item.id) for row in self.rows if row.item is not None]
        if len(set(items)) != len(items):
            raise ValueError('An item can be linked only once per tracker.')
        row_ids = [row.id for row in self.rows if row.id is not None]
        if len(set(row_ids)) != len(row_ids):
            raise ValueError('Row identifiers must be unique.')
        return self


class InvalidTrackerRow(ValueError):
    pass


def prepare_tracker_rows(data, previous):
    """Allocate stable row IDs and return the step transitions to publish."""
    previous_rows = (previous or {}).get('rows', [])
    old_rows = {
        row['id']: row for row in previous_rows if row.get('id')
    }
    old_steps = (previous or {}).get('steps', [])
    publish = data.get('timeline_sync', False)
    legacy_rows = len(old_rows) != len(previous_rows)
    changes = []
    for row in data['rows']:
        row_id = row.get('id')
        if row_id is not None and row_id not in old_rows:
            raise InvalidTrackerRow('A row identifier does not belong to this tracker.')
        row['id'] = row_id or uuid4().hex
        # A row without an ID in a legacy tracker has no reliable baseline.
        if not publish or (row_id is None and legacy_rows):
            continue
        old = old_rows.get(row_id)
        before = dict(zip(old_steps, old['completed'])) if old is not None else {}
        for step, completed in zip(data['steps'], row['completed']):
            if completed != before.get(step, False):
                changes.append((row, step, completed))
    return changes
