"""Persist the case tasks created from War Room tasks."""

import sqlalchemy as sa
from alembic import op

from app.alembic.alembic_utils import _has_table


revision = 'utmn_war_room_task_fan_out01'
down_revision = 'utmn_war_room_decisions01'
branch_labels = None
depends_on = None


def upgrade():
    if not _has_table('war_room_task_fan_out'):
        op.create_table(
            'war_room_task_fan_out',
            sa.Column('war_room_task_id', sa.BigInteger(),
                      sa.ForeignKey('war_room_task.task_id', ondelete='CASCADE'), primary_key=True),
            sa.Column('case_id', sa.BigInteger(),
                      sa.ForeignKey('cases.case_id', ondelete='CASCADE'), primary_key=True),
            sa.Column('case_task_id', sa.BigInteger(),
                      sa.ForeignKey('case_tasks.id', ondelete='CASCADE'), nullable=False),
        )
        op.create_index('ix_war_room_task_fan_out_case_task_id', 'war_room_task_fan_out', ['case_task_id'])


def downgrade():
    if _has_table('war_room_task_fan_out'):
        op.drop_table('war_room_task_fan_out')
