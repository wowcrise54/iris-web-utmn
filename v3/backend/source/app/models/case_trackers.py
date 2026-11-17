from sqlalchemy import Column, ForeignKey, Integer, JSON

from app.db import db


class CaseTracker(db.Model):
    __tablename__ = 'case_tracker'

    id = Column(Integer, primary_key=True)
    case_id = Column(ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    data = Column(JSON, nullable=False)

    __mapper_args__ = {'version_id_col': version}
