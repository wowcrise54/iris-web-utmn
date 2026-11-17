"""Index case timeline filters and text search."""

from alembic import op

from app.alembic.alembic_utils import index_exists


revision = 'utmn_timeline_search01'
down_revision = 'utmn_wazuh01'
branch_labels = None
depends_on = None

_TABLE = 'cases_events'
_ORDER_INDEX = 'ix_cases_events_case_id_event_date'
_TEXT_COLUMNS = ('event_title', 'event_content', 'event_source', 'event_tags')


def upgrade():
    if not index_exists(_TABLE, _ORDER_INDEX):
        op.create_index(_ORDER_INDEX, _TABLE, ['case_id', 'event_date', 'event_id'])
    if op.get_bind().dialect.name != 'postgresql':
        return

    op.execute("""
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
        EXCEPTION
            WHEN insufficient_privilege OR feature_not_supported THEN
                RAISE WARNING 'pg_trgm unavailable; timeline text search will run without trigram indexes';
        END $$;
    """)
    if not op.get_bind().exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'").scalar():
        return

    for column in _TEXT_COLUMNS:
        name = f'ix_cases_events_{column}_trgm'
        if not index_exists(_TABLE, name):
            op.create_index(name, _TABLE, [column], postgresql_using='gin',
                            postgresql_ops={column: 'gin_trgm_ops'})


def downgrade():
    for column in _TEXT_COLUMNS:
        name = f'ix_cases_events_{column}_trgm'
        if index_exists(_TABLE, name):
            op.drop_index(name, table_name=_TABLE)
    if index_exists(_TABLE, _ORDER_INDEX):
        op.drop_index(_ORDER_INDEX, table_name=_TABLE)
