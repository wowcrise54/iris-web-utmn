"""Alert-scoped derived analysis and explicit provider context window."""
from alembic import op
import sqlalchemy as sa

revision = 'utmn_alert_analysis01'
down_revision = 'utmn_maxpatrol03'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('evidence_analysis', sa.Column('alert_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_evidence_analysis_alert', 'evidence_analysis', 'alerts', ['alert_id'], ['alert_id'], ondelete='CASCADE')
    op.alter_column('evidence_analysis', 'case_id', existing_type=sa.BigInteger(), nullable=True)
    op.create_check_constraint('ck_evidence_analysis_scope', 'evidence_analysis', '(case_id IS NULL) <> (alert_id IS NULL)')
    op.create_index('ix_evidence_analysis_alert_id', 'evidence_analysis', ['alert_id'])
    op.create_index('uq_evidence_alert_analysis_active', 'evidence_analysis', ['requested_by', 'alert_id', 'source_key'], unique=True,
                    postgresql_where=sa.text("alert_id IS NOT NULL AND status IN ('queued', 'running')"))
    op.add_column('case_chat_conversation', sa.Column('alert_id', sa.BigInteger(), nullable=True))
    op.add_column('case_chat_conversation', sa.Column('alert_customer_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_case_chat_conversation_alert', 'case_chat_conversation', 'alerts', ['alert_id'], ['alert_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_case_chat_conversation_alert_customer', 'case_chat_conversation', 'client', ['alert_customer_id'], ['client_id'])
    op.create_check_constraint('ck_case_chat_alert_scope', 'case_chat_conversation', 'alert_id IS NULL OR (case_id IS NULL AND war_room_id IS NULL AND alert_customer_id IS NOT NULL)')
    for table, column in (('server_settings', 'chatbot_context_window_tokens'), ('chatbot_policy', 'context_window_tokens')):
        op.add_column(table, sa.Column(column, sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    # Dropping alert scope cannot preserve alert-only jobs/conversations.
    # Refuse a downgrade containing that data rather than silently deleting it.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM evidence_analysis WHERE alert_id IS NOT NULL) OR EXISTS (SELECT 1 FROM case_chat_conversation WHERE alert_id IS NOT NULL) THEN RAISE EXCEPTION 'Alert analysis data exists; downgrade would lose scope'; END IF; END $$")
    for table, column in (('server_settings', 'chatbot_context_window_tokens'), ('chatbot_policy', 'context_window_tokens')):
        op.drop_column(table, column)
    op.drop_constraint('ck_case_chat_alert_scope', 'case_chat_conversation', type_='check')
    op.drop_constraint('fk_case_chat_conversation_alert', 'case_chat_conversation', type_='foreignkey')
    op.drop_constraint('fk_case_chat_conversation_alert_customer', 'case_chat_conversation', type_='foreignkey')
    op.drop_column('case_chat_conversation', 'alert_customer_id')
    op.drop_column('case_chat_conversation', 'alert_id')
    op.drop_index('uq_evidence_alert_analysis_active', table_name='evidence_analysis')
    op.drop_index('ix_evidence_analysis_alert_id', table_name='evidence_analysis')
    op.drop_constraint('ck_evidence_analysis_scope', 'evidence_analysis', type_='check')
    op.alter_column('evidence_analysis', 'case_id', existing_type=sa.BigInteger(), nullable=False)
    op.drop_constraint('fk_evidence_analysis_alert', 'evidence_analysis', type_='foreignkey')
    op.drop_column('evidence_analysis', 'alert_id')
