"""Store an optional relation type on manual investigation graph edges."""

import sqlalchemy as sa
from alembic import op

from app.alembic.alembic_utils import _table_has_column


revision = 'utmn_graph_edge_relation01'
down_revision = 'utmn_war_room_task_fan_out01'
branch_labels = None
depends_on = None


TABLE = 'investigation_graph_edge'


def upgrade():
    if not _table_has_column(TABLE, 'relation'):
        op.add_column(TABLE, sa.Column('relation', sa.String(32), nullable=True))


def downgrade():
    if _table_has_column(TABLE, 'relation'):
        op.drop_column(TABLE, 'relation')
