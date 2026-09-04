"""add incident management fields per Tyumen State University Position

Revision ID: a1b2c3d4e5f6
Revises: e5d79b8c4a55
Create Date: 2026-08-28 15:00:00.000000

Idempotent: IRIS runs db.create_all() at startup, so the reference tables
may already exist (empty) before this migration runs. Every step is
guarded so the migration can be (re)applied safely.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e5d79b8c4a55'
branch_labels = None
depends_on = None

BIND = None


def bind():
    global BIND
    if BIND is None:
        BIND = op.get_bind()
    return BIND


def table_exists(table):
    return bool(bind().execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :t"
    ), {'t': table}).scalar())


def column_exists(table, column):
    return bool(bind().execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {'t': table, 'c': column}).scalar())


def fk_exists(constraint, table):
    return bool(bind().execute(text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE table_name = :t AND constraint_name = :c"
    ), {'t': table, 'c': constraint}).scalar())


INCIDENT_TABLES = {
    'incident_category': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    ],
    'system_type': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    ],
    'incident_importance': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    ],
    'incident_priority': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('level'),
    ],
    'incident_type': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    ],
    'undesirable_event': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ],
    'protagonist_motivation': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    ],
    'playbook': [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['incident_category.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
    ],
}

CASES_COLUMNS = [
    ('incident_category_id', sa.Integer()),
    ('system_type_id', sa.Integer()),
    ('importance_id', sa.Integer()),
    ('priority_id', sa.Integer()),
    ('incident_type_id', sa.Integer()),
    ('undesirable_event_id', sa.Integer()),
    ('is_undesirable_event', sa.Boolean()),
    ('investigation_start_date', sa.DateTime()),
    ('investigation_end_date', sa.DateTime()),
    ('impact_end_date', sa.DateTime()),
    ('investigation_completion_date', sa.DateTime()),
    ('reporter_name', sa.Text()),
    ('reporter_phone', sa.Text()),
    ('reporter_email', sa.Text()),
    ('reporter_location', sa.Text()),
    ('reporter_organization', sa.Text()),
    ('incident_occurrence_date', sa.DateTime()),
    ('incident_discovery_date', sa.DateTime()),
    ('incident_report_date', sa.DateTime()),
    ('incident_duration_seconds', sa.Integer()),
    ('response_phase', sa.Text()),
    ('playbook_id', sa.Integer()),
    ('affected_assets_info', sa.Text()),
    ('business_impact_description', sa.Text()),
    ('vulnerability_info', sa.Text()),
    ('perpetrator_description', sa.Text()),
    ('corrective_measures_org', sa.Text()),
    ('corrective_measures_tech', sa.Text()),
    ('investigation_report_path', sa.Text()),
    ('investigator_name', sa.Text()),
    ('motivation_id', sa.Integer()),
    ('resolution_actions_taken', sa.Text()),
    ('resolution_actions_planned', sa.Text()),
]

CASES_FOREIGN_KEYS = [
    ('fk_cases_incident_category', 'incident_category', ['incident_category_id'], ['id']),
    ('fk_cases_system_type', 'system_type', ['system_type_id'], ['id']),
    ('fk_cases_importance', 'incident_importance', ['importance_id'], ['id']),
    ('fk_cases_priority', 'incident_priority', ['priority_id'], ['id']),
    ('fk_cases_incident_type', 'incident_type', ['incident_type_id'], ['id']),
    ('fk_cases_undesirable_event', 'undesirable_event', ['undesirable_event_id'], ['id']),
    ('fk_cases_playbook', 'playbook', ['playbook_id'], ['id']),
    ('fk_cases_motivation', 'protagonist_motivation', ['motivation_id'], ['id']),
]

SEED_STATEMENTS = [
    """
        INSERT INTO incident_category (id, name, code, description) VALUES
        (1, 'Отказ систем, сервисов и сетей в обслуживании', 1, 'DoS/DDoS атаки, сбои сервисов'),
        (2, 'Внедрение вредоносного ПО', 2, 'Вирусы, трояны, ransomware'),
        (3, 'Несанкционированные попытки доступа', 3, 'Brute force, unauthorized access attempts'),
        (4, 'Разведка и рекогносцировка', 4, 'Scanning, reconnaissance activities'),
        (5, 'Несоблюдение требований ОРД по защите информации', 5, 'Policy violations'),
        (6, 'Нарушение мер физической защиты ИС', 6, 'Physical security breaches'),
        (7, 'Ошибка пользователя', 7, 'Accidental user actions'),
        (8, 'Иной тип инцидента', 8, 'Other incident types')
        ON CONFLICT (id) DO NOTHING
    """,
    """
        INSERT INTO system_type (id, name, code, description) VALUES
        (1, 'Целевая система', 1, 'Система, в результате воздействия на которую может произойти недопустимое событие'),
        (2, 'Ключевая система', 2, 'Система, доступ к которой необходим для развития атаки на целевую систему'),
        (3, 'Вспомогательная система', 3, 'Системы, обеспечивающие работу целевых и ключевых систем')
        ON CONFLICT (id) DO NOTHING
    """,
    """
        INSERT INTO incident_importance (id, name, code) VALUES
        (1, 'Высокая', 1),
        (2, 'Средняя', 2),
        (3, 'Низкая', 3)
        ON CONFLICT (id) DO NOTHING
    """,
    """
        INSERT INTO incident_priority (id, level) VALUES
        (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9)
        ON CONFLICT (id) DO NOTHING
    """,
    """
        INSERT INTO incident_type (id, category, name, code) VALUES
        (1, 'преднамеренный', 'Хищение', 1),
        (2, 'преднамеренный', 'Неправомерный доступ', 2),
        (3, 'преднамеренный', 'Мошенничество', 3),
        (4, 'преднамеренный', 'Неправомерное использование ресурсов', 4),
        (5, 'преднамеренный', 'Саботаж/Физический ущерб', 5),
        (6, 'преднамеренный', 'Неправомерное уничтожение информации', 6),
        (7, 'преднамеренный', 'Вредоносное программное обеспечение', 7),
        (8, 'преднамеренный', 'Другой случай', 8),
        (9, 'случайный', 'Отказ вычислительной и коммуникационной техники', 9),
        (10, 'случайный', 'Ошибка аппаратной поддержки', 10),
        (11, 'случайный', 'Отказ/ошибка ПО', 11),
        (12, 'случайный', 'Ошибка поддержки ПО', 12),
        (13, 'случайный', 'Ошибка пользователя', 13),
        (14, 'случайный', 'Недостаточное кадровое обеспечение', 14),
        (15, 'случайный', 'Отказ связи', 15),
        (16, 'случайный', 'Операционная ошибка', 16),
        (17, 'случайный', 'Отказ системы электропитания', 17),
        (18, 'случайный', 'Ошибка конструкции', 18),
        (19, 'случайный', 'Потеря существенных сервисов', 19),
        (20, 'случайный', 'Другой случай', 20),
        (21, 'естественный', 'Пожар', 21),
        (22, 'естественный', 'Техногенная авария', 22),
        (23, 'естественный', 'Наводнение', 23),
        (24, 'естественный', 'Стихийное бедствие', 24),
        (25, 'естественный', 'Другой случай', 25),
        (26, 'неизвестно', 'Неизвестно', 26)
        ON CONFLICT (id) DO NOTHING
    """,
    """
        INSERT INTO undesirable_event (id, name, description) VALUES
        (1, 'Утечка персональных данных', 'Компрометация ПДн'),
        (2, 'Утечка конфиденциальной информации', 'Разглашение конфиденциальных данных'),
        (3, 'Сбои или остановка операционных процессов из-за недоступности ИС', 'Operational disruption'),
        (4, 'Недоступность публичных систем', 'Public system unavailability'),
        (5, 'Вывод/потеря денежных средств со счета Университета', 'Financial loss'),
        (6, 'Публикация/предоставление недостоверной или противоправной информации', 'Information compromise')
        ON CONFLICT (id) DO NOTHING
    """,
    """
        INSERT INTO protagonist_motivation (id, name, code) VALUES
        (1, 'Криминальная/финансовая выгода', 1),
        (2, 'Политика/Терроризм', 2),
        (3, 'Развлечение/Хакерство', 3),
        (4, 'Неизвестен', 4),
        (5, 'Реванш', 5),
        (6, 'Нет виновного (природные факторы, отказ оборудования)', 6),
        (7, 'Другие мотивы', 7)
        ON CONFLICT (id) DO NOTHING
    """,
]


def upgrade():
    for table, columns in INCIDENT_TABLES.items():
        if not table_exists(table):
            op.create_table(table, *columns)

    for column, col_type in CASES_COLUMNS:
        if not column_exists('cases', column):
            op.add_column('cases', sa.Column(column, col_type, nullable=True))

    for constraint, ref_table, local_cols, ref_cols in CASES_FOREIGN_KEYS:
        if not fk_exists(constraint, 'cases'):
            op.create_foreign_key(constraint, 'cases', ref_table, local_cols, ref_cols)

    for statement in SEED_STATEMENTS:
        bind().execute(text(statement))


def downgrade():
    for constraint, ref_table, local_cols, ref_cols in reversed(CASES_FOREIGN_KEYS):
        if fk_exists(constraint, 'cases'):
            op.drop_constraint(constraint, 'cases')

    for column, _ in reversed(CASES_COLUMNS):
        if column_exists('cases', column):
            op.drop_column('cases', column)

    for table in ('playbook', 'protagonist_motivation', 'undesirable_event',
                  'incident_type', 'incident_priority', 'incident_importance',
                  'system_type', 'incident_category'):
        if table_exists(table):
            op.drop_table(table)
