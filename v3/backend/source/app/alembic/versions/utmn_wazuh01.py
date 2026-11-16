"""Persistent Wazuh collection state and deduplication."""
from alembic import op
import sqlalchemy as sa

revision = 'utmn_wazuh01'
down_revision = 'utmn_alert_analysis01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    expected = {
        'wazuh_poll_state': ({'source_key': sa.String, 'started_at': sa.DateTime,
                              'watermark': sa.DateTime, 'last_poll': sa.DateTime}, {'source_key'}),
        'wazuh_receipt': ({'source_key': sa.String, 'document_key': sa.String,
                           'alert_uuid': sa.Uuid}, {'source_key', 'document_key'}),
    }
    for table, (columns, primary_key) in expected.items():
        if inspector.has_table(table):
            actual = {column['name']: column for column in inspector.get_columns(table)}
            compatible = all(name in actual and isinstance(actual[name]['type'], kind)
                             and not actual[name]['nullable'] for name, kind in columns.items())
            if not compatible or set(inspector.get_pk_constraint(table)['constrained_columns']) != primary_key:
                raise RuntimeError(f'Existing {table} has an incompatible schema')
        elif table == 'wazuh_poll_state':
            op.create_table(table,
                sa.Column('source_key', sa.String(64), primary_key=True),
                sa.Column('started_at', sa.DateTime(), nullable=False),
                sa.Column('watermark', sa.DateTime(), nullable=False),
                sa.Column('last_poll', sa.DateTime(), nullable=False))
        else:
            op.create_table(table,
                sa.Column('source_key', sa.String(64), primary_key=True),
                sa.Column('document_key', sa.String(64), primary_key=True),
                sa.Column('alert_uuid', sa.Uuid(), nullable=False))


def downgrade():
    op.drop_table('wazuh_receipt')
    op.drop_table('wazuh_poll_state')
