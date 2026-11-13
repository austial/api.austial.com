import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from booking import migrate


def test_sync_url_conversion():
    assert migrate.sync_url("sqlite+aiosqlite:///./x.db") == "sqlite:///./x.db"
    assert migrate.sync_url("postgresql+asyncpg://u:p@h:25060/db?ssl=require") == "postgresql+psycopg://u:p@h:25060/db?sslmode=require"
    assert migrate.sync_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_migrations_build_the_entity_schema_with_no_drift(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    runner = migrate.runner(url)
    runner.upgrade("head")
    runner.upgrade("head")  # idempotent
    engine = sa.create_engine(migrate.sync_url(url))
    with engine.connect() as conn:
        tables = set(sa.inspect(conn).get_table_names())
        assert {"holds", "bookings", "leads", "alembic_version"} <= tables
        diff = compare_metadata(MigrationContext.configure(conn), migrate.metadata())
    assert diff == [], f"entities changed without a migration: {diff}"
