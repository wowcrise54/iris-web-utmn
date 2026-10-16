"""Persist Appendix 4 incident cards."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "utmn_incident_card01"
down_revision = "d2a6b8c1e374"
branch_labels = None
depends_on = None


def verify_existing_table(inspector):
    """Accept create_all's equivalent schema; refuse to stamp an unrelated table."""
    expected = {
        "case_id": (sa.BigInteger, False),
        "schema_version": (sa.Integer, False),
        "revision": (sa.Integer, False),
        "fields": (JSONB, False),
        "selections": (JSONB, False),
        "author_id": (sa.BigInteger, True),
        "author_name": (sa.Text, True),
        "created_at": (sa.DateTime, False),
        "updated_at": (sa.DateTime, False),
        "missing_sources": (JSONB, False),
    }
    columns = {
        column["name"]: column for column in inspector.get_columns("incident_cards")
    }
    if set(columns) != set(expected):
        raise RuntimeError("Existing incident_cards has incompatible columns")
    for name, (kind, nullable) in expected.items():
        column = columns[name]
        if not isinstance(column["type"], kind) or column["nullable"] != nullable:
            raise RuntimeError(
                "Existing incident_cards has incompatible column: " + name
            )
        if name in ("created_at", "updated_at") and not column["type"].timezone:
            raise RuntimeError(
                "Existing incident_cards timestamp lacks timezone: " + name
            )
    if inspector.get_pk_constraint("incident_cards").get("constrained_columns") != [
        "case_id"
    ]:
        raise RuntimeError("Existing incident_cards has incompatible primary key")
    foreign_keys = inspector.get_foreign_keys("incident_cards")
    for local, table, remote, ondelete in [
        ("case_id", "cases", "case_id", "CASCADE"),
        ("author_id", "user", "id", "SET NULL"),
    ]:
        if not any(
            key.get("constrained_columns") == [local]
            and key.get("referred_table") == table
            and key.get("referred_columns") == [remote]
            and str((key.get("options") or {}).get("ondelete", "")).upper() == ondelete
            for key in foreign_keys
        ):
            raise RuntimeError(
                "Existing incident_cards has incompatible foreign key: " + local
            )


def upgrade():
    # Startup currently creates registered model tables before running Alembic.
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("incident_cards"):
        verify_existing_table(inspector)
        return
    op.create_table(
        "incident_cards",
        sa.Column(
            "case_id",
            sa.BigInteger(),
            sa.ForeignKey("cases.case_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fields", JSONB(), nullable=False, server_default="{}"),
        sa.Column("selections", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "author_id", sa.BigInteger(), sa.ForeignKey("user.id", ondelete="SET NULL")
        ),
        sa.Column("author_name", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_sources", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_table("incident_cards")
