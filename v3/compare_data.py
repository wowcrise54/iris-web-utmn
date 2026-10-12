"""Compare existing business records without displaying their contents."""
import json
import subprocess
import os
from pathlib import Path

OLD = 'iris-upgrade-2-4-29-fastapi-db-1'
NEW = os.environ.get('IRIS_TARGET_DB', 'iris-v3-validation-20261010-db-1')

def sql(container, statement, database='iris_db'):
    output = subprocess.check_output(['docker', 'exec', container, 'psql', '-U', 'postgres', '-d', database,
                                      '-At', '-c', statement], text=True, encoding='utf-8')
    return json.loads(output)

tables = ['cases', 'alerts', 'client', 'notes', 'notes_group', 'case_assets', 'ioc', 'case_tasks',
          'task_assignee', 'cases_events', 'case_received_file', 'data_store_file',
          'custom_dashboard', 'custom_dashboard_widget']
baseline_file = Path(__file__).parent / 'runtime/data-baseline.json'
baseline = json.loads(baseline_file.read_text(encoding='utf-8')) if baseline_file.exists() else {}
report = {}
for table in tables:
    exists = table in baseline if baseline else sql(OLD, f"SELECT to_json(to_regclass('public.{table}') IS NOT NULL)")
    if not exists:
        continue
    old = baseline[table] if baseline else sql(OLD, f'SELECT COALESCE(json_agg(t),\'[]\'::json) FROM "{table}" t')
    new = sql(NEW, f'SELECT COALESCE(json_agg(t),\'[]\'::json) FROM "{table}" t')
    # New fields/rows are expected, but every saved source row must remain intact.
    for row in old:
        assert any(all(candidate.get(key) == value for key, value in row.items()) for candidate in new), \
            f'Saved record changed or missing in {table}'
    report[table] = {'source': len(old), 'target': len(new), 'all_saved_rows_preserved': True}
old_users = baseline['users'] if baseline else sql(OLD, 'SELECT json_agg(t) FROM (SELECT id, "user", password, active FROM "user") t')
new_users = sql(NEW, 'SELECT json_agg(t) FROM (SELECT id, "user", password, active FROM "user") t')
assert old_users == new_users, 'User identities or password hashes changed'
report['users'] = {'source': len(old_users), 'identities_and_password_hashes_preserved': True}
Path(__file__).with_name('data-comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
