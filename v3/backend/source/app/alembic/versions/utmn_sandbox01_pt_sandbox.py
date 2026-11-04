"""PT Sandbox scan history and original logs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'utmn_sandbox01'
down_revision = 'utmn_alert_materials01'
branch_labels = None
depends_on = None


def upgrade():
    # IRIS bootstrap calls metadata.create_all() before Alembic on existing databases.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('sandbox_scan'):
        _create_scan()
    if not inspector.has_table('sandbox_log'):
        _create_logs()


def _create_scan():
    op.create_table('sandbox_scan',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('case_id', sa.BigInteger(), sa.ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_id', sa.BigInteger(), sa.ForeignKey('data_store_file.file_id', ondelete='SET NULL')),
        sa.Column('war_room_id', sa.BigInteger(), sa.ForeignKey('war_room.war_room_id', ondelete='SET NULL')),
        sa.Column('topic_id', sa.BigInteger()),
        sa.Column('requested_by', sa.BigInteger(), sa.ForeignKey('user.id', ondelete='SET NULL')),
        sa.Column('module_id', sa.BigInteger(), sa.ForeignKey('iris_module.id', ondelete='SET NULL')),
        sa.Column('file_name', sa.Text(), nullable=False), sa.Column('sha256', sa.Text()),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('scan_id', sa.Text()), sa.Column('verdict', sa.Text()), sa.Column('error', sa.Text()),
        sa.Column('report', postgresql.JSONB()),
        sa.Column('options', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('finished_at', sa.DateTime()), sa.Column('notification_id', sa.BigInteger()))
    op.create_index('ix_sandbox_scan_case_id', 'sandbox_scan', ['case_id'])
    op.create_index('uq_sandbox_active_file', 'sandbox_scan', ['case_id', 'file_id'], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'uploading', 'submitting', 'running', 'collecting', 'submission_unknown')"))


def _create_logs():
    op.create_table('sandbox_log',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('scan_id', sa.BigInteger(), sa.ForeignKey('sandbox_scan.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_uri', sa.Text(), nullable=False), sa.Column('name', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False), sa.Column('size', sa.Integer()),
        sa.Column('sha256', sa.Text()), sa.Column('content', sa.LargeBinary()), sa.Column('error', sa.Text()))
    op.create_index('ix_sandbox_log_scan_id', 'sandbox_log', ['scan_id'])


def downgrade():
    op.drop_table('sandbox_log')
    op.drop_table('sandbox_scan')
