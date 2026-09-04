"""Delete E2E test cases (name like '%Incident E2E%') plus their child rows.

Multi-pass: child tables may reference each other (e.g. data_store_path ->
data_store_file), so we loop until no FK delete fails.

Run:
  docker compose run --rm -T app sh -c "cd /iriswebapp && PYTHONPATH=/iriswebapp python /dev/stdin" < source/app/e2e_cleanup.py
"""
from app import db, app as _app
from sqlalchemy import text
import os

with _app.app_context():
    explicit = os.environ.get("E2E_CLEANUP_IDS")
    if explicit:
        ids = [int(i) for i in explicit.split(",") if i.strip()]
        pattern = None
    else:
        pattern = "%Incident E2E%"
        ids = [r[0] for r in db.session.execute(
            text("SELECT case_id FROM cases WHERE name LIKE :p"), {"p": pattern})]
    print(f"[cleanup] deleting {len(ids)} cases: {ids}")
    if not ids:
        print("[cleanup] nothing to do")
    else:
        ph = ",".join(str(int(i)) for i in ids)
        fk_cols = db.session.execute(text(
            "SELECT conrelid::regclass::text, "
            "   (SELECT a.attname FROM pg_attribute a "
            "    WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)) "
            "FROM pg_constraint c WHERE c.contype = 'f' AND c.confrelid = 'cases'::regclass"
        )).fetchall()
        for _pass in range(5):
            remaining = 0
            for child, col in fk_cols:
                try:
                    db.session.execute(text(f'DELETE FROM "{child}" WHERE "{col}" IN ({ph})'))
                except Exception as e:
                    db.session.rollback()
                    remaining += 1
                    print(f"[cleanup] pass {_pass}: {child}.{col} blocked ({str(e)[:80]})")
            if remaining == 0:
                break
        db.session.execute(text(f'DELETE FROM cases WHERE case_id IN ({ph})'))
        db.session.commit()
        left = db.session.execute(
            text("SELECT count(*) FROM cases WHERE case_id IN (%s)" % ph)).scalar()
        print(f"[cleanup] done, cases remaining: {left}")
