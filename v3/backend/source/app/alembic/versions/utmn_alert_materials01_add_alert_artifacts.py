"""Investigation files and structured artifacts attached to alerts."""
from alembic import op
import sqlalchemy as sa

revision = 'utmn_alert_materials01'
down_revision = 'utmn_incident_card01'
branch_labels = None
depends_on = None


def upgrade():
    # PostInit runs metadata.create_all before Alembic, including on existing installations.
    if sa.inspect(op.get_bind()).has_table('alert_artifacts'):
        return
    op.create_table('alert_artifacts',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('alert_id', sa.BigInteger(), sa.ForeignKey('alerts.alert_id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('storage_name', sa.String(32)),
        sa.Column('size_bytes', sa.BigInteger()),
        sa.Column('sha256', sa.String(64)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_id', sa.BigInteger(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('updated_at', sa.DateTime()),
        sa.Column('updated_by_id', sa.BigInteger(), sa.ForeignKey('user.id')),
        sa.Column('include_in_case', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index('ix_alert_artifacts_alert_id', 'alert_artifacts', ['alert_id'])


def downgrade():
    op.drop_table('alert_artifacts')
