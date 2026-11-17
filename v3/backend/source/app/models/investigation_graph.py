from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db import db


class InvestigationGraphNode(db.Model):
    __tablename__ = 'investigation_graph_node'

    id = Column(Integer, primary_key=True)
    case_id = Column(ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    label = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)


class InvestigationGraphEdge(db.Model):
    __tablename__ = 'investigation_graph_edge'

    id = Column(Integer, primary_key=True)
    case_id = Column(ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    source = Column(String(32), nullable=False)
    target = Column(String(32), nullable=False)
    label = Column(String(200), nullable=False)
    directed = Column(Boolean, nullable=False)
    evidence = relationship(
        'InvestigationGraphEvidence', cascade='all, delete-orphan', lazy='selectin',
        passive_deletes=True,
    )


class InvestigationGraphEvidence(db.Model):
    __tablename__ = 'investigation_graph_evidence'

    edge_id = Column(ForeignKey('investigation_graph_edge.id', ondelete='CASCADE'), primary_key=True)
    event_id = Column(ForeignKey('cases_events.event_id', ondelete='CASCADE'), primary_key=True)


class InvestigationGraphView(db.Model):
    __tablename__ = 'investigation_graph_view'

    id = Column(Integer, primary_key=True)
    case_id = Column(ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    label = Column(String(200), nullable=False)
    state = Column(JSON, nullable=False)
