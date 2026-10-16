"""Persistent scans and original logs; case deletion cascades to both."""
from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey, LargeBinary, Integer, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from app.db import db


class SandboxScan(db.Model):
    __tablename__ = 'sandbox_scan'
    id = Column(BigInteger, primary_key=True)
    case_id = Column(BigInteger, ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    file_id = Column(BigInteger, ForeignKey('data_store_file.file_id', ondelete='SET NULL'))
    war_room_id = Column(BigInteger, ForeignKey('war_room.war_room_id', ondelete='SET NULL'))
    topic_id = Column(BigInteger)
    requested_by = Column(BigInteger, ForeignKey('user.id', ondelete='SET NULL'))
    module_id = Column(BigInteger, ForeignKey('iris_module.id', ondelete='SET NULL'))
    file_name = Column(Text, nullable=False)
    sha256 = Column(Text)
    status = Column(Text, nullable=False, server_default='queued')
    scan_id = Column(Text)
    verdict = Column(Text)
    error = Column(Text)
    report = Column(JSONB)
    options = Column(JSONB, nullable=False, server_default='{}')
    created_at = Column(DateTime, nullable=False, server_default=text('now()'))
    updated_at = Column(DateTime, nullable=False, server_default=text('now()'))
    finished_at = Column(DateTime)
    notification_id = Column(BigInteger)
    __table_args__ = (Index('uq_sandbox_active_file', 'case_id', 'file_id', unique=True,
                           postgresql_where=text("status IN ('queued', 'uploading', 'submitting', 'running', 'collecting', 'submission_unknown')")),)


class SandboxLog(db.Model):
    __tablename__ = 'sandbox_log'
    id = Column(BigInteger, primary_key=True)
    scan_id = Column(BigInteger, ForeignKey('sandbox_scan.id', ondelete='CASCADE'), nullable=False, index=True)
    file_uri = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    size = Column(Integer)
    sha256 = Column(Text)
    content = Column(LargeBinary)
    error = Column(Text)
