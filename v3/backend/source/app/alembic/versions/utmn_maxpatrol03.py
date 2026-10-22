"""Restore inline alert events while retaining the previously applied migration chain."""
from alembic import op

revision = 'utmn_maxpatrol03'
down_revision = 'utmn_maxpatrol02'
branch_labels = None
depends_on = None


def upgrade():
    # Recover evidence before removing the separate-store marker, entirely inside PostgreSQL.
    op.execute("""
        UPDATE alerts a SET alert_source_content = (
            (a.alert_source_content::jsonb - 'event_storage') || jsonb_build_object(
                'events', COALESCE((
                    SELECT jsonb_agg(jsonb_strip_nulls(e.payload) ORDER BY e.event_key)
                    FROM maxpatrol_event_record e WHERE e.alert_uuid = a.alert_uuid
                ), '[]'::jsonb),
                'event_collection', jsonb_build_object(
                    'version', 2, 'complete', false, 'source', 'restored_inline', 'errors', '[]'::jsonb)
            )
        )::json
        WHERE a.alert_source = 'MaxPatrol SIEM'
          AND a.alert_source_content::jsonb #>> '{event_storage,kind}' = 'maxpatrol'
    """)
    op.execute("""
        UPDATE iris_module m SET module_config = COALESCE((
            SELECT jsonb_agg(p.value ORDER BY p.ordinality)
            FROM jsonb_array_elements(m.module_config::jsonb) WITH ORDINALITY p(value, ordinality)
            WHERE COALESCE(p.value->>'param_name', '') NOT IN (
                'event_page_size', 'max_events_per_poll', 'max_response_mb',
                'max_bytes_per_poll_mb', 'max_incidents_per_poll', 'max_requests_per_poll')
        ), '[]'::jsonb)::json
        WHERE m.module_name = 'iris_maxpatrol_module'
          AND jsonb_typeof(m.module_config::jsonb) = 'array'
    """)
    # Keep the former tables as evidence backup; the collector no longer accesses them.


def downgrade():
    # The inline copy is safe to keep; the old event store has not been deleted.
    pass
