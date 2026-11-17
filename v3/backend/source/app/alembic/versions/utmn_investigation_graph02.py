"""Persist analyst-authored case graph nodes, edges and views."""

import sqlalchemy as sa
from alembic import op

from app.alembic.alembic_utils import _has_table


revision = 'utmn_investigation_graph02'
down_revision = 'utmn_investigation_graph01'
branch_labels = None
depends_on = None


def _case_columns():
    return (
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_id', sa.BigInteger(), sa.ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False),
    )


def upgrade():
    node = 'investigation_graph_node'
    edge = 'investigation_graph_edge'
    evidence = 'investigation_graph_evidence'
    view = 'investigation_graph_view'

    if not _has_table(node):
        op.create_table(node, *_case_columns(),
                        sa.Column('label', sa.String(200), nullable=False),
                        sa.Column('description', sa.Text(), nullable=False))
        op.create_index(f'ix_{node}_case_id', node, ['case_id'])
    if not _has_table(edge):
        op.create_table(edge, *_case_columns(),
                        sa.Column('source', sa.String(32), nullable=False),
                        sa.Column('target', sa.String(32), nullable=False),
                        sa.Column('label', sa.String(200), nullable=False),
                        sa.Column('directed', sa.Boolean(), nullable=False))
        op.create_index(f'ix_{edge}_case_id', edge, ['case_id'])
    if not _has_table(evidence):
        op.create_table(evidence,
                        sa.Column('edge_id', sa.Integer(), sa.ForeignKey(f'{edge}.id', ondelete='CASCADE'),
                                  primary_key=True),
                        sa.Column('event_id', sa.BigInteger(),
                                  sa.ForeignKey('cases_events.event_id', ondelete='CASCADE'), primary_key=True))
    if not _has_table(view):
        op.create_table(view, *_case_columns(),
                        sa.Column('label', sa.String(200), nullable=False),
                        sa.Column('state', sa.JSON(), nullable=False))
        op.create_index(f'ix_{view}_case_id', view, ['case_id'])


def downgrade():
    op.drop_table('investigation_graph_evidence')
    op.drop_table('investigation_graph_view')
    op.drop_table('investigation_graph_edge')
    op.drop_table('investigation_graph_node')
