from sqlalchemy import Column, ForeignKey

from app.db import db


class WarRoomTaskFanOut(db.Model):
    __tablename__ = 'war_room_task_fan_out'

    war_room_task_id = Column(ForeignKey('war_room_task.task_id', ondelete='CASCADE'), primary_key=True)
    case_id = Column(ForeignKey('cases.case_id', ondelete='CASCADE'), primary_key=True)
    case_task_id = Column(ForeignKey('case_tasks.id', ondelete='CASCADE'), nullable=False, index=True)
