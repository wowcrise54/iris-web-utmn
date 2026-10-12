"""Read persisted schema directly, without importing app or rerunning bootstrap."""
import json
import os
import psycopg2
connection = psycopg2.connect(host=os.environ['POSTGRES_SERVER'], port=os.environ.get('POSTGRES_PORT', '5432'),
    dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'])
connection.set_session(readonly=True, autocommit=True)
with connection.cursor() as cursor:
    cursor.execute('SELECT version_num FROM alembic_version')
    heads = [row[0] for row in cursor.fetchall()]
    assert heads == ['e5d79b8c4a55'], heads
    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('custom_dashboard', 'custom_dashboard_widget') ORDER BY tablename")
    tables = [row[0] for row in cursor.fetchall()]
    assert tables == ['custom_dashboard', 'custom_dashboard_widget'], tables
connection.close()
print(json.dumps({'persisted_alembic_heads': heads, 'persisted_dashboard_tables': tables}))
