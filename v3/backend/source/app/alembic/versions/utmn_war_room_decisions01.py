"""Add the append-only decision journal for War Rooms."""

import sqlalchemy as sa
from alembic import op

from app.alembic.alembic_utils import _has_table


revision = 'utmn_war_room_decisions01'
down_revision = 'utmn_case_trackers01'
branch_labels = None
depends_on = None


def upgrade():
    if not _has_table('war_room_decision'):
        op.create_table(
            'war_room_decision',
            sa.Column('id', sa.BigInteger(), primary_key=True),
            sa.Column('war_room_id', sa.BigInteger(),
                      sa.ForeignKey('war_room.war_room_id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(256), nullable=False),
            sa.Column('rationale', sa.Text(), nullable=False),
            sa.Column('status', sa.String(16), nullable=False),
            sa.Column('history', sa.JSON(), nullable=False),
        )
        op.create_index('ix_war_room_decision_war_room_id', 'war_room_decision', ['war_room_id'])


def downgrade():
    if _has_table('war_room_decision'):
        op.drop_table('war_room_decision')
