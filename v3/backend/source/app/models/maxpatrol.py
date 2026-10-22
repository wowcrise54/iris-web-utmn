"""Persistent import receipts intentionally survive module and alert deletion."""
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db import db


class MaxPatrolPollState(db.Model):
    __tablename__ = 'maxpatrol_poll_state'
    source_key = Column(String(64), primary_key=True)
    last_poll = Column(DateTime, nullable=False)


class MaxPatrolReceipt(db.Model):
    __tablename__ = 'maxpatrol_receipt'
    source_key = Column(String(64), primary_key=True)
    incident_id = Column(String(512), primary_key=True)
    alert_uuid = Column(UUID(as_uuid=True), nullable=False)
    imported_at = Column(DateTime, nullable=False)
