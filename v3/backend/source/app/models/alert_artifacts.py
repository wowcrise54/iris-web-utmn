from datetime import datetime

from app.db import db
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship


class AlertArtifact(db.Model):
    __tablename__ = 'alert_artifacts'

    id = Column(BigInteger, primary_key=True)
    alert_id = Column(ForeignKey('alerts.alert_id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default='')
    storage_name = Column(String(32))
    size_bytes = Column(BigInteger)
    sha256 = Column(String(64))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_id = Column(ForeignKey('user.id'), nullable=False)
    updated_at = Column(DateTime)
    updated_by_id = Column(ForeignKey('user.id'))
    include_in_case = Column(Boolean, nullable=False, default=True)

    alert = relationship('Alert', back_populates='artifacts')
    created_by = relationship('User', foreign_keys=[created_by_id])

    def serialize(self):
        return {**{key: getattr(self, key) for key in (
            'id', 'alert_id', 'kind', 'value', 'description', 'size_bytes', 'sha256',
            'created_by_id', 'updated_by_id', 'include_in_case')},
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by_name': self.created_by.name if self.created_by else None}
