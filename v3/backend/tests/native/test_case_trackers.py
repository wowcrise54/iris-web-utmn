import sys
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import Column, Integer, String, create_engine, inspect
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.orm.exc import StaleDataError


def tracker_schema():
    module = Path(__file__).resolve().parents[2] / 'source/app/business/case_trackers.py'
    return run_path(str(module))['TrackerSchema']


def test_tracker_preserves_configured_columns_and_step_state():
    data = tracker_schema().model_validate({
        'name': ' Host response ',
        'columns': ['Owner', 'Network'],
        'steps': ['Isolate', 'Recover'],
        'rows': [{'label': 'host-1', 'values': ['SOC', 'DMZ'], 'completed': [True, False]}],
    }).model_dump()
    assert data['name'] == 'Host response'
    assert data['rows'][0]['values'] == ['SOC', 'DMZ']
    assert data['rows'][0]['completed'] == [True, False]


@pytest.mark.parametrize('changes', [
    {'steps': ['Isolate', 'isolate']},
    {'name': '   '},
    {'rows': [{'label': 'host-1', 'values': [], 'completed': [False]}]},
    {'rows': [{'label': 'host-1', 'values': ['SOC'], 'completed': [1]}]},
])
def test_tracker_rejects_invalid_configuration_and_row_state(changes):
    with pytest.raises(ValidationError):
        tracker_schema().model_validate({
            'name': 'Response', 'columns': ['Owner'], 'steps': ['Isolate'], 'rows': [],
        } | changes)


def test_tracker_accepts_existing_manual_rows_and_unique_case_item_references():
    row = {'label': 'host-1', 'values': [], 'completed': [False]}
    asset = {**row, 'item': {'kind': 'asset', 'id': 17}}
    data = {'name': 'Response', 'columns': [], 'steps': ['Isolate'], 'rows': [row, asset]}
    parsed = tracker_schema().model_validate(data).model_dump()
    assert parsed['rows'][0]['item'] is None
    assert parsed['rows'][1]['item'] == {'kind': 'asset', 'id': 17}
    with pytest.raises(ValidationError):
        tracker_schema().model_validate({**data, 'rows': [asset, asset]})
    with pytest.raises(ValidationError):
        tracker_schema().model_validate({**data, 'rows': [{**row, 'item': {'kind': 'case', 'id': 17}}]})


def test_timeline_records_only_changed_steps_and_survives_row_reordering():
    module = Path(__file__).resolve().parents[2] / 'source/app/business/case_trackers.py'
    prepare = run_path(str(module))['prepare_tracker_rows']
    first = {'label': 'Host A', 'completed': [True], 'values': []}
    second = {'label': 'Host B', 'completed': [False], 'values': []}
    original = {'name': 'Response', 'steps': ['Isolate'], 'timeline_sync': True, 'rows': [first, second]}
    assert [(row['label'], step, completed) for row, step, completed in prepare(original, None)] == [
        ('Host A', 'Isolate', True),
    ]
    edited = {**original, 'rows': [{**second}, {**first, 'label': 'Renamed host', 'completed': [False]}]}
    changes = prepare(edited, original)
    assert [(row['label'], step, completed) for row, step, completed in changes] == [
        ('Renamed host', 'Isolate', False),
    ]
    assert prepare(edited, edited) == []
    assert prepare({**edited, 'timeline_sync': False}, original) == []
    assert prepare(original, {**original, 'timeline_sync': False}) == []
    assert len(prepare(edited, {**original, 'timeline_sync': False})) == 1
    legacy = {'steps': ['Isolate'], 'rows': [{'label': 'Host A', 'completed': [True], 'values': []}]}
    assert prepare({**legacy, 'timeline_sync': True, 'rows': [dict(legacy['rows'][0])]}, legacy) == []


def test_tracker_storage_scopes_updates_and_prevents_lost_edits(monkeypatch):
    base = declarative_base()

    class Cases(base):
        __tablename__ = 'cases'
        case_id = Column(Integer, primary_key=True)

    class Item(base):
        __tablename__ = 'test_items'
        id = Column(Integer, primary_key=True)
        owner = Column(Integer, nullable=False)
        label = Column(String, nullable=False)

    source = Path(__file__).resolve().parents[2] / 'source/app'
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        db = SimpleNamespace(Model=base, session=session)
        monkeypatch.setitem(sys.modules, 'app.db', SimpleNamespace(db=db))
        models = run_path(str(source / 'models/case_trackers.py'))
        tracker_model = models['CaseTracker']
        tracker_model.query = session.query(tracker_model)
        monkeypatch.setitem(sys.modules, 'app.models.case_trackers', SimpleNamespace(CaseTracker=tracker_model))
        monkeypatch.setitem(sys.modules, 'app.models.assets', SimpleNamespace(
            CaseAssets=SimpleNamespace(asset_id=Item.id, case_id=Item.owner, asset_name=Item.label),
        ))
        monkeypatch.setitem(sys.modules, 'app.models.evidences', SimpleNamespace(
            CaseReceivedFile=SimpleNamespace(id=Item.id, case_id=Item.owner, filename=Item.label),
        ))
        monkeypatch.setitem(sys.modules, 'app.models.iocs', SimpleNamespace(
            Ioc=SimpleNamespace(ioc_id=Item.id, case_id=Item.owner, ioc_value=Item.label),
        ))
        monkeypatch.setitem(sys.modules, 'app.models.models', SimpleNamespace(
            CaseTasks=SimpleNamespace(id=Item.id, task_case_id=Item.owner, task_title=Item.label),
        ))
        items = run_path(str(source / 'datamgmt/case/case_tracker_items_db.py'))
        monkeypatch.setitem(sys.modules, 'app.datamgmt.case.case_tracker_items_db', SimpleNamespace(**items))
        business = run_path(str(source / 'business/case_trackers.py'))
        monkeypatch.setitem(sys.modules, 'app.business.case_trackers', SimpleNamespace(**business))
        timeline_calls = []
        monkeypatch.setitem(sys.modules, 'app.datamgmt.case.case_tracker_timeline_db', SimpleNamespace(
            append_tracker_events=lambda *args: timeline_calls.append(args),
        ))
        persistence = run_path(str(source / 'datamgmt/case/case_trackers_db.py'))
        save = persistence['save_tracker']
        Cases.__table__.create(engine)
        Item.__table__.create(engine)
        with engine.begin() as connection:
            helpers = SimpleNamespace(_has_table=lambda name: inspect(connection).has_table(name))
            monkeypatch.setitem(sys.modules, 'app.alembic.alembic_utils', helpers)
            migration = run_path(str(source / 'alembic/versions/utmn_case_trackers01.py'))
            with Operations.context(MigrationContext.configure(connection)):
                migration['upgrade']()
                migration['upgrade']()
                migration['downgrade']()
                assert not inspect(connection).has_table('case_tracker')
                migration['upgrade']()
        session.add_all([
            Cases(case_id=1), Cases(case_id=2),
            Item(id=11, owner=1, label='Host%1'), Item(id=12, owner=2, label='Host%2'),
        ])
        session.add_all(Item(id=item_id, owner=1, label='Target') for item_id in range(20, 71))
        session.commit()
        for kind in ['asset', 'ioc', 'task', 'evidence']:
            assert items['list_tracker_items'](1, kind, 'HOST%', 0) == {
                'items': [{'kind': kind, 'id': 11, 'label': 'Host%1'}], 'next_after': None,
            }
        first_page = items['list_tracker_items'](1, 'asset', 'target', 0)
        assert [item['id'] for item in first_page['items']] == list(range(20, 70))
        assert first_page['next_after'] == 69
        assert items['list_tracker_items'](1, 'asset', 'target', 69) == {
            'items': [{'kind': 'asset', 'id': 70, 'label': 'Target'}], 'next_after': None,
        }

        data = {'name': 'Response', 'columns': [], 'steps': ['Isolate'], 'rows': []}
        created = save(1, None, None, data)
        identifier = created['id']
        assert persistence['list_trackers'](2) == []
        assert save(2, identifier, 1, data) is None
        assert save(2, identifier, 1, None) is None

        row = {'label': 'host-1', 'values': [], 'completed': [True]}
        with pytest.raises(items['InvalidTrackerItem']):
            save(1, identifier, 1, {**data, 'rows': [{**row, 'item': {'kind': 'asset', 'id': 12}}]})
        changed = {**data, 'rows': [{**row, 'item': {'kind': 'asset', 'id': 11}}]}
        saved = save(1, identifier, 1, changed)
        assert saved['version'] == 2
        assert saved['rows'] == changed['rows']
        with pytest.raises(StaleDataError):
            save(1, identifier, 1, data)
        with pytest.raises(StaleDataError):
            save(1, identifier, 1, None)
        assert persistence['list_trackers'](1) == [saved]
        session.delete(session.get(Item, 11))
        session.commit()
        updated = save(1, identifier, 2, {**changed, 'name': 'Updated'})
        assert updated['rows'] == changed['rows']
        enabled = save(1, identifier, 3, {**changed, 'timeline_sync': True}, user_id=15)
        assert timeline_calls == []
        reopened = {**enabled, 'rows': [{**enabled['rows'][0], 'completed': [False]}]}
        saved = save(1, identifier, 4, {key: reopened[key] for key in (*changed, 'timeline_sync')}, user_id=15)
        assert saved['version'] == 5
        assert timeline_calls == [
            (1, identifier, 'Response', 15, [(saved['rows'][0], 'Isolate', False)]),
        ]
