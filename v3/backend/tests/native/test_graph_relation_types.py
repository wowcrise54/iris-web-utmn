import logging
import sys
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest
from sqlalchemy import Boolean, Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base


def test_catalog_preserves_system_types_and_rejects_deleting_used_types(monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'source/app'
    base = declarative_base()

    class Relation(base):
        __tablename__ = 'relations'
        id = Column(Integer, primary_key=True)
        name = Column(String, unique=True)
        label = Column(String)
        description = Column(String)
        directed = Column(Boolean)
        color = Column(String)
        line_style = Column(String)
        stix_relationship = Column(String)
        is_system = Column(Boolean)
        sort_order = Column(Integer)

    class Edge(base):
        __tablename__ = 'edges'
        edge_id = Column(Integer, primary_key=True)
        relation_type_id = Column(Integer)

    engine = create_engine('sqlite://')
    base.metadata.create_all(engine)
    with Session(engine) as session:
        Relation.query = session.query(Relation)
        Edge.query = session.query(Edge)
        monkeypatch.setitem(sys.modules, 'app.db', SimpleNamespace(db=SimpleNamespace(session=session)))
        monkeypatch.setitem(sys.modules, 'app.models.case_graph', SimpleNamespace(
            CaseGraphRelationType=Relation, CaseGraphEdge=Edge,
            CASE_GRAPH_LINE_STYLES=('solid', 'dashed', 'dotted'),
        ))
        monkeypatch.setitem(sys.modules, 'app.logger', SimpleNamespace(logger=logging.getLogger(__name__)))
        errors = run_path(str(source / 'models/errors.py'))
        monkeypatch.setitem(sys.modules, 'app.models.errors', SimpleNamespace(**errors))
        monkeypatch.setitem(sys.modules, 'app.iris_engine.utils.tracker', SimpleNamespace(track_activity=lambda *a, **k: None))
        persistence = run_path(str(source / 'datamgmt/case/case_graph_relations_db.py'))
        monkeypatch.setitem(sys.modules, 'app.datamgmt.case.case_graph_relations_db', SimpleNamespace(**persistence))
        business = run_path(str(source / 'business/case_graph_relation_types.py'))
        system = Relation(name='related_to', label='Related to', is_system=True, sort_order=0)
        session.add(system)
        session.commit()
        with pytest.raises(errors['BusinessProcessingError']):
            business['case_graph_relation_types_update'](system.id, {'name': 'changed'})
        session.rollback()
        custom = business['case_graph_relation_types_create']({'name': 'observed_on', 'label': 'Observed on'})
        session.add(Edge(relation_type_id=custom['id']))
        session.commit()
        with pytest.raises(errors['BusinessProcessingError']):
            business['case_graph_relation_types_delete'](custom['id'])
        listed = business['case_graph_relation_types_list']()
        assert next(row for row in listed if row['id'] == custom['id'])['edge_count'] == 1
        ids = [row['id'] for row in listed]
        with pytest.raises(errors['BusinessProcessingError']):
            business['case_graph_relation_types_reorder']([ids[0], ids[0]])
        assert [row['id'] for row in business['case_graph_relation_types_reorder'](ids[::-1])] == ids[::-1]
