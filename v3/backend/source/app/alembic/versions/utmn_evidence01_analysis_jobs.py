"""Bounded Sandbox and PCAP analysis jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'utmn_evidence01'
down_revision = 'utmn_sandbox01'
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('evidence_analysis'):
        return
    op.create_table('evidence_analysis',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('case_id', sa.BigInteger(), sa.ForeignKey('cases.case_id', ondelete='CASCADE'), nullable=False),
        sa.Column('requested_by', sa.BigInteger(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', sa.BigInteger(), sa.ForeignKey('case_chat_conversation.id', ondelete='SET NULL')),
        sa.Column('message_id', sa.BigInteger(), sa.ForeignKey('case_chat_message.id', ondelete='SET NULL')),
        sa.Column('kind', sa.Text(), nullable=False), sa.Column('source_key', sa.Text(), nullable=False),
        sa.Column('source', JSONB(), nullable=False), sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('result', JSONB(), nullable=False, server_default='{}'), sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')))
    op.create_index('ix_evidence_analysis_case_id', 'evidence_analysis', ['case_id'])
    op.create_index('uq_evidence_analysis_active', 'evidence_analysis', ['requested_by', 'case_id', 'source_key'],
                    unique=True, postgresql_where=sa.text("status IN ('queued', 'running')"))


def downgrade():
    op.drop_table('evidence_analysis')
