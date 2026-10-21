"""Persistent import receipts intentionally survive module and alert deletion."""
from sqlalchemy import Column, String, DateTime, JSON, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db import db


class MaxPatrolPollState(db.Model):
    __tablename__ = 'maxpatrol_poll_state'
    source_key = Column(String(64), primary_key=True)
    last_poll = Column(DateTime, nullable=False)
    discovery = Column(JSON, nullable=True)


class MaxPatrolReceipt(db.Model):
    __tablename__ = 'maxpatrol_receipt'
    source_key = Column(String(64), primary_key=True)
    incident_id = Column(String(512), primary_key=True)
    alert_uuid = Column(UUID(as_uuid=True), nullable=False)
    imported_at = Column(DateTime, nullable=False)


class MaxPatrolIngestState(db.Model):
    __tablename__ = 'maxpatrol_ingest_state'
    source_key = Column(String(64), primary_key=True)
    incident_id = Column(String(512), primary_key=True)
    incident = Column(JSON, nullable=False)
    cursor = Column(JSON, nullable=True)
    last_attempt = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, nullable=False, default=False)
    legacy_migrated = Column(Boolean, nullable=False, default=False)


class MaxPatrolEventRecord(db.Model):
    __tablename__ = 'maxpatrol_event_record'
    source_key = Column(String(64), primary_key=True)
    incident_id = Column(String(512), primary_key=True)
    event_key = Column(String(80), primary_key=True)
    alert_uuid = Column(ForeignKey('alerts.alert_uuid', ondelete='CASCADE'), nullable=False, index=True)
    payload = Column(JSON().with_variant(JSONB(), 'postgresql'), nullable=False)
    byte_size = Column(Integer, nullable=False)
