"""Restore inline alert events while retaining the previously applied migration chain."""
from alembic import op
import sqlalchemy as sa

revision = 'utmn_maxpatrol03'
down_revision = 'utmn_maxpatrol02'
branch_labels = None
depends_on = None
MAX_INLINE_BYTES = 8 * 1024 * 1024


def upgrade():
    # Measure individual rows first. Never aggregate a large archive into one JSONB container.
    op.execute(sa.text("""
        WITH sizes AS (
            SELECT a.alert_uuid, count(e.alert_uuid) AS event_count,
                   COALESCE(sum(octet_length(e.payload::text)), 0) AS total_bytes
            FROM alerts a LEFT JOIN maxpatrol_event_record e ON e.alert_uuid = a.alert_uuid
            WHERE a.alert_source = 'MaxPatrol SIEM'
              AND a.alert_source_content::jsonb #>> '{event_storage,kind}' = 'maxpatrol'
            GROUP BY a.alert_uuid
        )
        UPDATE alerts a SET alert_source_content = (CASE
          WHEN sizes.total_bytes + octet_length(a.alert_source_content::text) <= :max_inline_bytes THEN
            (a.alert_source_content::jsonb - 'event_storage') || jsonb_build_object(
                'events', COALESCE((
                    SELECT jsonb_agg(jsonb_strip_nulls(e.payload) ORDER BY e.event_key)
                    FROM maxpatrol_event_record e WHERE e.alert_uuid = a.alert_uuid
                ), '[]'::jsonb),
                'event_collection', jsonb_build_object(
                    'version', 2, 'complete', false, 'source', 'restored_inline', 'errors', '[]'::jsonb)
            )
          ELSE a.alert_source_content::jsonb || jsonb_build_object(
                'event_storage', jsonb_build_object(
                    'kind', 'maxpatrol', 'archived_only', true,
                    'count', sizes.event_count, 'bytes', sizes.total_bytes),
                'event_collection', jsonb_build_object(
                    'version', 2, 'complete', false, 'source', 'retained_event_archive',
                    'refresh_blocked', true, 'inline_limit_bytes', :max_inline_bytes,
                    'errors', jsonb_build_array(jsonb_build_object('reason', 'legacy_payload_too_large')))
            )
          END)::json
        FROM sizes WHERE a.alert_uuid = sizes.alert_uuid
    """).bindparams(max_inline_bytes=MAX_INLINE_BYTES))
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
