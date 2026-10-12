"""Online startup migrations must persist under SQLAlchemy 2 autobegin."""
import ast
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, text


def test_online_migration_commits_revision(tmp_path):
    path = Path(__file__).parents[2] / "source/app/alembic/env.py"
    tree = ast.parse(path.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "run_migrations_online")
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num TEXT)"))
    state = {}

    def configure(**kwargs):
        state["connection"] = kwargs["connection"]

    def run_migrations():
        state["connection"].execute(text("INSERT INTO alembic_version VALUES ('head')"))

    namespace = dict(
        engine_from_config=lambda *args, **kwargs: engine,
        config=SimpleNamespace(config_ini_section="alembic", get_section=lambda _: {}),
        pool=SimpleNamespace(NullPool=None), target_metadata=None,
        context=SimpleNamespace(configure=configure, run_migrations=run_migrations),
    )
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    namespace["run_migrations_online"]()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "head"
