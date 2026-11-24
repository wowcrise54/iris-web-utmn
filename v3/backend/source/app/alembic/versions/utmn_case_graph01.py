#  IRIS Source Code
#  Copyright (C) 2026 - DFIR-IRIS
#  contact@dfir-iris.org

"""Create the beta.23 graph schema alongside existing investigation graph data."""
import sqlalchemy as sa
from alembic import op
from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from sqlalchemy.dialects import postgresql

from app.alembic.alembic_utils import _has_table


revision = 'utmn_case_graph01'
down_revision = 'utmn_graph_edge_relation01'
branch_labels = None
depends_on = None


_RELATION_TYPES = (
    ('related_to', 'Related to', False, 'slate', 'dashed', 'related-to'),
    ('co_occurs', 'Seen together', False, 'slate', 'dashed', 'related-to'),
    ('connected_to', 'Connected to', True, 'sky', 'solid', 'communicates-with'),
    ('authenticated_to', 'Authenticated to', True, 'indigo', 'solid', 'related-to'),
    ('lateral_movement', 'Lateral movement', True, 'red', 'solid', 'related-to'),
    ('executed_on', 'Executed on', True, 'orange', 'solid', 'related-to'),
    ('dropped', 'Dropped', True, 'amber', 'solid', 'drops'),
    ('downloaded_from', 'Downloaded from', True, 'amber', 'solid', 'downloads'),
    ('resolves_to', 'Resolves to', True, 'teal', 'solid', 'resolves-to'),
    ('beacons_to', 'Beacons to', True, 'rose', 'solid', 'beacons-to'),
    ('exfiltrated_to', 'Exfiltrated to', True, 'fuchsia', 'solid', 'exfiltrates-to'),
    ('owns_account', 'Owns account', True, 'violet', 'solid', 'related-to'),
    ('same_as', 'Same as', False, 'emerald', 'dotted', 'duplicate-of'),
    ('parent_of', 'Parent of', True, 'gray', 'dotted', 'related-to'),
    ('involved_in', 'Involved in', True, 'slate', 'dotted', 'related-to'),
)


def _user_fk(name):
    return sa.Column(name, sa.BigInteger(), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)


def _case_fk(primary_key=False):
    return sa.Column('case_id', sa.BigInteger(), sa.ForeignKey('cases.case_id', ondelete='CASCADE'),
                     nullable=False, primary_key=primary_key)


def _tlp_fk():
    return sa.Column('tlp_id', sa.Integer(), sa.ForeignKey('tlp.tlp_id', ondelete='SET NULL'), nullable=True)


def _timestamps():
    return [
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    ]


def _create_relation_types():
    if not _has_table('case_graph_relation_type'):
        op.create_table(
            'case_graph_relation_type',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(64), nullable=False, unique=True),
            sa.Column('label', sa.Text(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('directed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('color', sa.String(16), nullable=False, server_default=sa.text("'slate'")),
            sa.Column('line_style', sa.String(16), nullable=False, server_default=sa.text("'solid'")),
            sa.Column('stix_relationship', sa.String(64), nullable=True),
            sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.CheckConstraint("line_style IN ('solid', 'dashed', 'dotted')",
                               name='ck_case_graph_relation_type_line_style'),
        )
    bind = op.get_bind()
    for position, (name, label, directed, color, line_style, stix) in enumerate(_RELATION_TYPES):
        bind.execute(
            sa.text('INSERT INTO case_graph_relation_type '
                    '(name, label, directed, color, line_style, stix_relationship, is_system, sort_order) '
                    'VALUES (:name, :label, :directed, :color, :line_style, :stix, true, :sort_order) '
                    'ON CONFLICT (name) DO NOTHING'),
            {'name': name, 'label': label, 'directed': directed, 'color': color,
             'line_style': line_style, 'stix': stix, 'sort_order': position},
        )


def _create_nodes():
    if _has_table('case_graph_node'):
        return
    op.create_table(
        'case_graph_node',
        sa.Column('node_id', sa.BigInteger(), primary_key=True),
        sa.Column('node_uuid', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        _case_fk(),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('node_type', sa.String(32), nullable=False, server_default=sa.text("'other'")),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(64), nullable=True),
        sa.Column('color', sa.String(16), nullable=True),
        _tlp_fk(),
        sa.Column('custom_attributes', postgresql.JSONB(), nullable=True),
        _user_fk('created_by_id'),
        *_timestamps(),
    )
    op.create_index('ix_case_graph_node_case_id', 'case_graph_node', ['case_id'])


def _create_edges():
    if not _has_table('case_graph_edge'):
        op.create_table(
            'case_graph_edge',
            sa.Column('edge_id', sa.BigInteger(), primary_key=True),
            sa.Column('edge_uuid', postgresql.UUID(as_uuid=True), nullable=False,
                      server_default=sa.text('gen_random_uuid()')),
            _case_fk(),
            sa.Column('source_kind', sa.String(16), nullable=False),
            sa.Column('source_id', sa.BigInteger(), nullable=False),
            sa.Column('target_kind', sa.String(16), nullable=False),
            sa.Column('target_id', sa.BigInteger(), nullable=False),
            sa.Column('relation_type_id', sa.Integer(), sa.ForeignKey('case_graph_relation_type.id'),
                      nullable=False),
            sa.Column('directed', sa.Boolean(), nullable=False),
            sa.Column('label', sa.Text(), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('confidence', sa.SmallInteger(), nullable=True),
            sa.Column('first_seen', sa.DateTime(), nullable=True),
            sa.Column('last_seen', sa.DateTime(), nullable=True),
            _tlp_fk(),
            sa.Column('origin', sa.String(16), nullable=False, server_default=sa.text("'manual'")),
            sa.Column('review_state', sa.String(16), nullable=False, server_default=sa.text("'accepted'")),
            sa.Column('custom_attributes', postgresql.JSONB(), nullable=True),
            _user_fk('created_by_id'),
            *_timestamps(),
            sa.CheckConstraint('NOT (source_kind = target_kind AND source_id = target_id)',
                               name='ck_case_graph_edge_no_loop'),
            sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 100)',
                               name='ck_case_graph_edge_confidence'),
        )
        op.create_index('ix_case_graph_edge_case_id', 'case_graph_edge', ['case_id'])
        op.create_index('idx_case_graph_edge_source', 'case_graph_edge', ['case_id', 'source_kind', 'source_id'])
        op.create_index('idx_case_graph_edge_target', 'case_graph_edge', ['case_id', 'target_kind', 'target_id'])

    if not _has_table('case_graph_edge_event'):
        op.create_table(
            'case_graph_edge_event',
            sa.Column('edge_id', sa.BigInteger(), sa.ForeignKey('case_graph_edge.edge_id', ondelete='CASCADE'),
                      primary_key=True, nullable=False),
            sa.Column('event_id', sa.BigInteger(), sa.ForeignKey('cases_events.event_id', ondelete='CASCADE'),
                      primary_key=True, nullable=False),
        )
        op.create_index('ix_case_graph_edge_event_event_id', 'case_graph_edge_event', ['event_id'])


def _create_dismissed_suggestions():
    if _has_table('case_graph_dismissed_suggestion'):
        return
    op.create_table(
        'case_graph_dismissed_suggestion',
        _case_fk(primary_key=True),
        sa.Column('suggestion_key', sa.String(255), primary_key=True, nullable=False),
        _user_fk('dismissed_by_id'),
        sa.Column('dismissed_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )


def _create_views():
    if _has_table('case_graph_view'):
        return
    op.create_table(
        'case_graph_view',
        sa.Column('view_id', sa.BigInteger(), primary_key=True),
        sa.Column('view_uuid', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        _case_fk(),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        _user_fk('owner_id'),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_report_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('state', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('snapshot', sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index('ix_case_graph_view_case_id', 'case_graph_view', ['case_id'])


def upgrade():
    _create_relation_types()
    _create_nodes()
    _create_edges()
    _create_dismissed_suggestions()
    _create_views()
    _copy_existing_graph()


def _copy_existing_graph():
    bind = op.get_bind()
    if not _has_table('investigation_graph_node'):
        return
    # Legacy revisions can commit the database transaction without clearing Alembic's
    # transaction object. Start a real transaction if the PostgreSQL driver is idle.
    if bind.connection.driver_connection.get_transaction_status() == TRANSACTION_STATUS_IDLE:
        bind.exec_driver_sql('BEGIN')
    # Hold the previous graph stable until this transaction installs the new API schema.
    bind.execute(sa.text(
        'LOCK TABLE investigation_graph_node, investigation_graph_edge, '
        'investigation_graph_evidence, investigation_graph_view IN SHARE ROW EXCLUSIVE MODE'
    ))
    unknown_relation = bind.execute(sa.text("""
        SELECT e.id FROM investigation_graph_edge e
        LEFT JOIN case_graph_relation_type r ON r.name = COALESCE(e.relation, 'related_to')
        WHERE r.id IS NULL LIMIT 1
    """)).scalar()
    if unknown_relation is not None:
        raise RuntimeError(f'Cannot migrate graph edge {unknown_relation}: unknown relation type')
    bind.execute(sa.text("""
        INSERT INTO case_graph_node(node_id, case_id, label, description)
        SELECT id, case_id, label, description FROM investigation_graph_node
        ON CONFLICT (node_id) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO case_graph_edge(
            edge_id, case_id, source_kind, source_id, target_kind, target_id,
            relation_type_id, directed, label
        )
        SELECT e.id, e.case_id, split_part(e.source, ':', 1),
               split_part(e.source, ':', 2)::bigint, split_part(e.target, ':', 1),
               split_part(e.target, ':', 2)::bigint, r.id, e.directed, e.label
        FROM investigation_graph_edge e
        JOIN case_graph_relation_type r ON r.name = COALESCE(e.relation, 'related_to')
        ON CONFLICT (edge_id) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO case_graph_edge_event(edge_id, event_id)
        SELECT edge_id, event_id FROM investigation_graph_evidence
        ON CONFLICT (edge_id, event_id) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO case_graph_view(view_id, case_id, name, state, is_shared)
        SELECT id, case_id, label, state::jsonb, true FROM investigation_graph_view
        ON CONFLICT (view_id) DO NOTHING
    """))
    for table, column in (
        ('case_graph_node', 'node_id'), ('case_graph_edge', 'edge_id'), ('case_graph_view', 'view_id'),
    ):
        bind.execute(sa.text(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
            f"COALESCE(MAX({column}), 1), MAX({column}) IS NOT NULL) FROM {table}"
        ))


def downgrade():
    for table in ('case_graph_view', 'case_graph_dismissed_suggestion', 'case_graph_edge_event',
                  'case_graph_edge', 'case_graph_node', 'case_graph_relation_type'):
        if _has_table(table):
            op.drop_table(table)
