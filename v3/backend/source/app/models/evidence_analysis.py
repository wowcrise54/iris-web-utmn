"""Derived, bounded analysis jobs; original evidence remains in its existing storage."""
from sqlalchemy import Column, BigInteger, Text, Integer, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from app.db import db


class EvidenceAnalysis(db.Model):
    __tablename__ = 'evidence_analysis'
    id = Column(BigInteger, primary_key=True)
    case_id = Column(BigInteger, ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False, index=True)
    requested_by = Column(BigInteger, ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    conversation_id = Column(BigInteger, ForeignKey('case_chat_conversation.id', ondelete='SET NULL'))
    message_id = Column(BigInteger, ForeignKey('case_chat_message.id', ondelete='SET NULL'))
    kind = Column(Text, nullable=False)
    source_key = Column(Text, nullable=False)
    source = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, server_default='queued')
    progress = Column(Integer, nullable=False, server_default='0')
    total = Column(Integer, nullable=False, server_default='0')
    result = Column(JSONB, nullable=False, server_default='{}')
    error = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=text('now()'))
    updated_at = Column(DateTime, nullable=False, server_default=text('now()'))
    __table_args__ = (Index('uq_evidence_analysis_active', 'requested_by', 'case_id', 'source_key', unique=True,
                           postgresql_where=text("status IN ('queued', 'running')")),)
