"""Index existing MaxPatrol alert IOCs for the related-alerts graph."""
from alembic import op


revision = 'utmn_alert_ioc_cache01'
down_revision = 'utmn_case_graph01'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        INSERT INTO similar_alerts_cache (customer_id, alert_id, ioc_value, ioc_type_id, created_at)
        SELECT DISTINCT a.alert_customer_id, a.alert_id, i.ioc_value, i.ioc_type_id, a.alert_source_event_time
        FROM alerts a
        JOIN alert_iocs_association ai ON ai.alert_id = a.alert_id
        JOIN ioc i ON i.ioc_id = ai.ioc_id
        WHERE a.alert_source IN ('MaxPatrol SIEM', 'MaxPatrol EDR')
          AND i.ioc_value IS NOT NULL AND i.ioc_type_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM similar_alerts_cache c
              WHERE c.alert_id = a.alert_id AND c.customer_id = a.alert_customer_id
                AND c.ioc_value = i.ioc_value AND c.ioc_type_id = i.ioc_type_id
          )
    ''')


def downgrade():
    # The inserted rows are valid cache entries in the previous revision too.
    pass
