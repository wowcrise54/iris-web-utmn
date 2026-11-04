"""Restore inline alert events while retaining the previously applied migration chain."""
from alembic import op
import sqlalchemy as sa

revision = 'utmn_maxpatrol03'
down_revision = 'utmn_maxpatrol02'
branch_labels = None
depends_on = None
MAX_INLINE_BYTES = 8 * 1024 * 1024


def upgrade():
    # JSON can exceed JSONB's container limit. Preserve the original without parsing/casting it.
    op.execute("""
        CREATE TABLE IF NOT EXISTS maxpatrol_payload_archive (
            archive_id BIGSERIAL PRIMARY KEY,
            alert_uuid UUID NOT NULL,
            payload JSON NOT NULL,
            payload_bytes BIGINT NOT NULL,
            archived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute('CREATE INDEX IF NOT EXISTS ix_maxpatrol_payload_archive_alert_uuid '
               'ON maxpatrol_payload_archive (alert_uuid)')
    op.execute(sa.text("""
        WITH archived AS (
            INSERT INTO maxpatrol_payload_archive (alert_uuid, payload, payload_bytes)
            SELECT alert_uuid, alert_source_content, octet_length(alert_source_content::text)
            FROM alerts
            WHERE alert_source = 'MaxPatrol SIEM'
              AND octet_length(alert_source_content::text) > :max_inline_bytes
            RETURNING archive_id, alert_uuid, payload_bytes
        )
        UPDATE alerts a SET alert_source_content = json_build_object(
            'event_storage', json_build_object(
                'kind', 'maxpatrol', 'archived_only', true,
                'payload_archive_id', archived.archive_id, 'payload_bytes', archived.payload_bytes),
            'event_collection', json_build_object(
                'version', 2, 'complete', false, 'refresh_blocked', true,
                'source', 'retained_payload_archive', 'inline_limit_bytes', :max_inline_bytes,
                'errors', json_build_array(json_build_object('reason', 'legacy_payload_too_large')))
        )
        FROM archived WHERE a.alert_uuid = archived.alert_uuid
    """).bindparams(max_inline_bytes=MAX_INLINE_BYTES))
    # Measure individual rows first. Never aggregate a large archive into one JSONB container.
    op.execute(sa.text("""
        WITH small_sources AS MATERIALIZED (
            SELECT a.alert_uuid, a.alert_source_content FROM alerts a
            WHERE a.alert_source = 'MaxPatrol SIEM'
              AND CASE WHEN octet_length(a.alert_source_content::text) <= :max_inline_bytes
                  THEN a.alert_source_content #>> '{event_storage,kind}' = 'maxpatrol'
                   AND a.alert_source_content #>> '{event_storage,payload_archive_id}' IS NULL
                  ELSE false END
        ), sizes AS (
            SELECT a.alert_uuid, count(e.alert_uuid) AS event_count,
                   COALESCE(sum(octet_length(e.payload::text)), 0) AS total_bytes
            FROM small_sources a LEFT JOIN maxpatrol_event_record e ON e.alert_uuid = a.alert_uuid
            GROUP BY a.alert_uuid
        )
        UPDATE alerts a SET alert_source_content = (CASE
          WHEN sizes.total_bytes + octet_length(small.alert_source_content::text) <= :max_inline_bytes THEN
            (small.alert_source_content::jsonb - 'event_storage') || jsonb_build_object(
                'events', COALESCE((
                    SELECT jsonb_agg(jsonb_strip_nulls(e.payload) ORDER BY e.event_key)
                    FROM maxpatrol_event_record e WHERE e.alert_uuid = a.alert_uuid
                ), '[]'::jsonb),
                'event_collection', jsonb_build_object(
                    'version', 2, 'complete', false, 'source', 'restored_inline', 'errors', '[]'::jsonb)
            )
          ELSE small.alert_source_content::jsonb || jsonb_build_object(
                'event_storage', jsonb_build_object(
                    'kind', 'maxpatrol', 'archived_only', true,
                    'count', sizes.event_count, 'bytes', sizes.total_bytes),
                'event_collection', jsonb_build_object(
                    'version', 2, 'complete', false, 'source', 'retained_event_archive',
                    'refresh_blocked', true, 'inline_limit_bytes', :max_inline_bytes,
                    'errors', jsonb_build_array(jsonb_build_object('reason', 'legacy_payload_too_large')))
            )
          END)::json
        FROM sizes JOIN small_sources small ON small.alert_uuid = sizes.alert_uuid
        WHERE a.alert_uuid = sizes.alert_uuid
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
