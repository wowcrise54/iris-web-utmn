"""Translate v2.4 permission meanings before applying v3 additions."""
from alembic import op
from sqlalchemy import text

revision = 'utmn_v3_permissions01'
down_revision = 'e5d79b8c4a55'
branch_labels = None
depends_on = None

V2_FULL = 0xffff
V3_FULL = 0xfffffff

def translate_mask(mask):
    if mask == V2_FULL:
        return V3_FULL
    # The first twelve permissions keep their meanings. Statistics now lives
    # in dashboards; preserve read access without granting write/share access.
    result = mask & 0xfff
    if mask & (0x1000 | 0x2000):
        result |= 0x1000
    if mask & 0x4000:
        result |= 0x2000
    if mask & 0x8000:
        result |= 0x4000
    return result

def upgrade():
    connection = op.get_bind()
    for group_id, mask in connection.execute(text('SELECT group_id, group_permissions FROM groups')):
        connection.execute(text('UPDATE groups SET group_permissions = :mask WHERE group_id = :id'),
                           {'mask': translate_mask(mask), 'id': group_id})

def downgrade():
    raise RuntimeError('Restore the preserved PG12 snapshot to roll back across the v2/v3 schema boundary')
