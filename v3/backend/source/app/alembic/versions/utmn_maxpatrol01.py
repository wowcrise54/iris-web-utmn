"""Persistent MaxPatrol polling and import state (no existing data changes)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'utmn_maxpatrol01'
down_revision = 'utmn_card_appendix4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('maxpatrol_poll_state',
        sa.Column('source_key', sa.String(64), primary_key=True),
        sa.Column('last_poll', sa.DateTime(), nullable=False))
    op.create_table('maxpatrol_receipt',
        sa.Column('source_key', sa.String(64), primary_key=True),
        sa.Column('incident_id', sa.String(512), primary_key=True),
        sa.Column('alert_uuid', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('imported_at', sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table('maxpatrol_receipt')
    op.drop_table('maxpatrol_poll_state')
