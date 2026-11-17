from sqlalchemy import BigInteger, Column, ForeignKey, JSON, String, Text

from app.db import db


class WarRoomDecision(db.Model):
    __tablename__ = 'war_room_decision'

    id = Column(BigInteger, primary_key=True)
    war_room_id = Column(ForeignKey('war_room.war_room_id', ondelete='CASCADE'), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    rationale = Column(Text, nullable=False)
    status = Column(String(16), nullable=False)
    history = Column(JSON, nullable=False)
