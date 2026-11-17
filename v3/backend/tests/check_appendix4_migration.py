"""Run the actual cleanup revision on a restored, disposable database only."""

import importlib.util
import json
import os
from pathlib import Path
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

db_name = "iris_card_restore_check"
assert db_name != "iris_db"
url = sa.URL.create(
    "postgresql+psycopg2",
    username=os.getenv("POSTGRES_USER", "postgres"),
    password=os.environ["POSTGRES_PASSWORD"],
    host="db",
    database=db_name,
)
engine = sa.create_engine(url)
root = Path("/candidate/source/app")
spec = importlib.util.spec_from_file_location(
    "cleanup_revision", root / "alembic/versions/utmn_card_appendix4.py"
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
with engine.begin() as conn:
    # Fingerprint every other application table, not just case/alert counts.
    tables = [
        t
        for t in sa.inspect(conn).get_table_names()
        if t not in ("incident_cards", "alembic_version")
    ]

    def fingerprint():
        return {
            t: conn.execute(
                sa.text(
                    "SELECT md5(coalesce(string_agg(r::text,'' ORDER BY r::text),'')) FROM (SELECT row_to_json(x) AS r FROM \""
                    + t
                    + '" x) s'
                )
            ).scalar()
            for t in tables
        }

    before = fingerprint()
    original = {
        "description": dict(value="Сохранить описание", mode="manual"),
        "files": dict(value="удалить", mode="auto"),
        "title": dict(value="удалить заголовок", mode="manual"),
        "reporter_address": dict(
            value="не переносить неоднозначный адрес", mode="manual"
        ),
        "performed_actions": dict(
            value="Выполненная задача", mode="auto", source="task:4"
        ),
        "report_url": dict(value="https://example.test/report", mode="manual"),
        "report_location": dict(value="Архив", mode="manual"),
        "investigators": dict(
            value=[dict(name="И" * 500, position="А" * 500) for _ in range(50)],
            mode="manual",
        ),
    }
    conn.execute(
        sa.text(
            "INSERT INTO incident_cards (case_id,schema_version,revision,fields,selections,created_at,updated_at,missing_sources) VALUES (3,1,1,CAST(:fields AS jsonb),'{\"file_ids\":[4]}'::jsonb,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'[\"file_ids\"]'::jsonb)"
        ),
        dict(fields=json.dumps(original, ensure_ascii=False)),
    )
    context = MigrationContext.configure(conn)
    with Operations.context(context):
        migration.upgrade()
    row = (
        conn.execute(sa.text("SELECT * FROM incident_cards WHERE case_id=3"))
        .mappings()
        .one()
    )
    assert (
        row["selections"] == {}
        and row["missing_sources"] == []
        and row["revision"] == 2
    )
    assert row["fields"]["description"]["value"] == "Сохранить описание"
    assert row["fields"]["performed_actions"]["mode"] == "manual"
    assert row["fields"]["performed_actions"]["source"] is None
    assert row["fields"]["report_url"]["value"] == "https://example.test/report\nАрхив"
    assert len(row["fields"]["investigators"]["value"]) > 50000
    assert not set(row["fields"]) & {
        "files",
        "title",
        "reporter_address",
        "incident_location",
    }
    assert fingerprint() == before, "Cleanup changed another application table"
    conn.execute(sa.text("DELETE FROM incident_cards WHERE case_id=3"))
print(
    "Actual migration passed on restored database; all other tables unchanged; legacy investigator text retained."
)
