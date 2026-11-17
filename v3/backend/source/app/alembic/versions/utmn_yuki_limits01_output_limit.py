"""Configurable Yuki output limit; zero uses the provider's maximum/default."""
from alembic import op
import sqlalchemy as sa

revision = 'utmn_yuki_limits01'
down_revision = 'utmn_evidence01'
branch_labels = None
depends_on = None


def upgrade():
    for table, column in (('server_settings', 'chatbot_max_output_tokens'), ('chatbot_policy', 'max_output_tokens')):
        if column not in {item['name'] for item in sa.inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, sa.Column(column, sa.Integer(), nullable=False, server_default=sa.text('2048')))


def downgrade():
    for table, column in (('server_settings', 'chatbot_max_output_tokens'), ('chatbot_policy', 'max_output_tokens')):
        if column in {item['name'] for item in sa.inspect(op.get_bind()).get_columns(table)}:
            op.drop_column(table, column)
