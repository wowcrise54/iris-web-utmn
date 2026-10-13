"""Case-scoped persisted incident card; attribution is server owned."""

from app.db import db
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB


class IncidentCard(db.Model):
    __tablename__ = "incident_cards"
    case_id = Column(
        BigInteger, ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True
    )
    schema_version = Column(Integer, nullable=False, default=1)
    revision = Column(Integer, nullable=False, default=1)
    fields = Column(JSONB, nullable=False, default=dict)
    selections = Column(JSONB, nullable=False, default=dict)
    author_id = Column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    author_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    missing_sources = Column(JSONB, nullable=False, default=list)
