"""Durable Wazuh collection watermarks and receipts."""
from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from app.db import db


class WazuhPollState(db.Model):
    __tablename__ = 'wazuh_poll_state'
    source_key = Column(String(64), primary_key=True)
    started_at = Column(DateTime, nullable=False)
    watermark = Column(DateTime, nullable=False)
    last_poll = Column(DateTime, nullable=False)


class WazuhReceipt(db.Model):
    __tablename__ = 'wazuh_receipt'
    source_key = Column(String(64), primary_key=True)
    document_key = Column(String(64), primary_key=True)
    alert_uuid = Column(UUID(as_uuid=True), nullable=False)
