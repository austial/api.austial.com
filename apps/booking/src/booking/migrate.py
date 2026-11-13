"""Schema migrations through the framework's Alembic runner.

    python -m booking.migrate upgrade            apply every pending migration (what the container runs on start)
    python -m booking.migrate revision "message" create a migration from entity changes (review it before committing)
    python -m booking.migrate current|history

Reads DATABASE_URL like the app does. The app talks to the database asynchronously, Alembic synchronously,
so the URL is converted to a sync driver here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from austial.migrations import MigrationRunner, MigrationsConfig
from austial.orm import DataSource
from austial.orm.driver import SQLiteDriver

from .entities import ENTITIES

SCRIPT_LOCATION = str(Path(__file__).resolve().parents[2] / "migrations")
DEFAULT_URL = "sqlite+aiosqlite:///./booking.db"


def sync_url(url: str) -> str:
    """asyncpg/aiosqlite URL to the sync driver Alembic needs (psycopg for Postgres)."""
    if url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite+aiosqlite", "sqlite", 1)
    for prefix in ("postgresql+asyncpg://", "postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    # asyncpg spells it ssl=, libpq/psycopg spells it sslmode=
    return url.replace("?ssl=", "?sslmode=").replace("&ssl=", "&sslmode=")


def metadata():
    # Only the schema is read from the entities; this never connects.
    return DataSource(SQLiteDriver(DEFAULT_URL), ENTITIES).get_metadata()


def runner(url: str | None = None) -> MigrationRunner:
    return MigrationRunner(
        sync_url(url or os.getenv("DATABASE_URL") or DEFAULT_URL),
        metadata=metadata(),
        config=MigrationsConfig(script_location=SCRIPT_LOCATION),
    )


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "upgrade"
    r = runner()
    if cmd == "upgrade":
        r.upgrade("head")
        print(f"database is at {r.current()}")
    elif cmd == "revision":
        if len(argv) < 2:
            print('usage: python -m booking.migrate revision "message"', file=sys.stderr)
            return 2
        print("created", r.revision(argv[1]))
    elif cmd == "current":
        print(r.current())
    elif cmd == "history":
        for row in r.history():
            print(row)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
