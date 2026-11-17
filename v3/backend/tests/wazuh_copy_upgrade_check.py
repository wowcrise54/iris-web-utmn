"""Exercise the complete Alembic upgrade ONLY against an isolated PGDATA copy."""
import os
if os.environ.get('WAZUH_DISPOSABLE_TEST_DB') != 'yes':
    raise RuntimeError('Set WAZUH_DISPOSABLE_TEST_DB=yes only for an isolated disposable database')

import sys
import types
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

engine = create_engine('postgresql://postgres@127.0.0.1/iris_wazuh_test')
with engine.connect() as connection:
    if connection.scalar(text("SHOW data_directory")) != '/tmp/pgcopy':
        raise RuntimeError('Refusing to touch a database outside the temporary copy')
    if connection.scalar(text('SELECT version_num FROM alembic_version')) != 'utmn_card_appendix4':
        raise RuntimeError('Unexpected starting revision in temporary copy')
    before = {table: connection.scalar(text(
        f"SELECT coalesce(md5(string_agg(md5(row_to_json(t)::text), '' ORDER BY {key})), '') FROM {table} t"))
        for table, key in [('cases', 'case_id'), ('alerts', 'alert_id')]}

app = types.ModuleType('app')
app.__path__ = ['/source/app']
configuration = types.ModuleType('app.configuration')
configuration.SQLALCHEMY_BASE_ADMIN_URI = 'postgresql://postgres@127.0.0.1/'
configuration.PG_DB_ = 'iris_wazuh_test'
sys.modules['app'] = app
sys.modules['app.configuration'] = configuration
# Older migrations import application helpers while Alembic discovers every
# revision; these older revisions are not run from this database version.
for name, attributes in {
    'app.models.cases': ['CaseState'],
    'app.models.assets': ['CompromiseStatus'],
    'app.iris_engine.access_control.utils': ['ac_get_mask_analyst', 'ac_get_mask_case_access_level_full',
                                              'ac_get_mask_full_permissions'],
}.items():
    module = types.ModuleType(name)
    for attribute in attributes:
        setattr(module, attribute, object())
    sys.modules[name] = module
cfg = Config('/source/app/alembic.ini')
cfg.set_main_option('script_location', '/source/app/alembic')
command.upgrade(cfg, 'head')

with engine.connect() as connection:
    revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
    after = {table: connection.scalar(text(
        f"SELECT coalesce(md5(string_agg(md5(row_to_json(t)::text), '' ORDER BY {key})), '') FROM {table} t"))
        for table, key in [('cases', 'case_id'), ('alerts', 'alert_id')]}
    print(f'revision={revision}; case_rows_unchanged={before["cases"] == after["cases"]}; '
          f'alert_rows_unchanged={before["alerts"] == after["alerts"]}')
