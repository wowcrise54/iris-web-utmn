"""Store case response trackers and their revision counters."""

import sqlalchemy as sa
from alembic import op

from app.alembic.alembic_utils import _has_table


revision = 'utmn_case_trackers01'
down_revision = 'utmn_investigation_graph02'
branch_labels = None
depends_on = None


def upgrade():
    if not _has_table('case_tracker'):
        op.create_table(
            'case_tracker',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('case_id', sa.BigInteger(), sa.ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('data', sa.JSON(), nullable=False),
        )
        op.create_index('ix_case_tracker_case_id', 'case_tracker', ['case_id'])


def downgrade():
    if _has_table('case_tracker'):
        op.drop_table('case_tracker')
