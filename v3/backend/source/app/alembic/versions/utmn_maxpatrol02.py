"""Bounded MaxPatrol ingestion cursors and single-copy event storage."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'utmn_maxpatrol02'
down_revision = 'utmn_maxpatrol01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('maxpatrol_poll_state', sa.Column('discovery', sa.JSON(), nullable=True))
    op.create_table('maxpatrol_ingest_state',
        sa.Column('source_key', sa.String(64), primary_key=True),
        sa.Column('incident_id', sa.String(512), primary_key=True),
        sa.Column('incident', sa.JSON(), nullable=False),
        sa.Column('cursor', sa.JSON(), nullable=True),
        sa.Column('last_attempt', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('legacy_migrated', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('maxpatrol_event_record',
        sa.Column('source_key', sa.String(64), primary_key=True),
        sa.Column('incident_id', sa.String(512), primary_key=True),
        sa.Column('event_key', sa.String(80), primary_key=True),
        sa.Column('alert_uuid', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('alerts.alert_uuid', ondelete='CASCADE'), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False))
    op.create_index('ix_maxpatrol_event_record_alert_uuid', 'maxpatrol_event_record', ['alert_uuid'])


def downgrade():
    op.drop_table('maxpatrol_event_record')
    op.drop_table('maxpatrol_ingest_state')
    op.drop_column('maxpatrol_poll_state', 'discovery')
