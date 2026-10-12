"""Repair permission semantics on the first rehearsal after inspecting v3's grants."""
import importlib.util
from app import app
from app.db import db
from sqlalchemy import text

spec = importlib.util.spec_from_file_location('permissions', '/tmp/permissions.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
with app.app_context(), db.engine.begin() as connection:
    for group_id, mask in connection.execute(text('SELECT group_id, group_permissions FROM groups')):
        upstream_added = mask & 0xe000000
        previous = mask & ~0xe000000
        assert previous <= 0xffff, 'Unexpected rehearsal permission mask'
        connection.execute(text('UPDATE groups SET group_permissions = :mask WHERE group_id = :id'),
                           {'mask': migration.translate_mask(previous) | upstream_added, 'id': group_id})
print('Rehearsal permission semantics restored')
