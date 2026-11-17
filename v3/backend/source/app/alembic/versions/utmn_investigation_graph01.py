"""Store source and target roles on event associations."""

import sqlalchemy as sa
from alembic import op

from app.alembic.alembic_utils import _table_has_column


revision = 'utmn_investigation_graph01'
down_revision = 'utmn_timeline_search01'
branch_labels = None
depends_on = None

TABLES = ('case_events_assets', 'case_events_ioc')


def upgrade():
    for table in TABLES:
        if not _table_has_column(table, 'role'):
            op.add_column(table, sa.Column(
                'role', sa.String(16), nullable=False, server_default='involved',
            ))


def downgrade():
    for table in TABLES:
        op.drop_column(table, 'role')
