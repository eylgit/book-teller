"""Run the migrations: the files that make and change the tables.

Alembic is the migration tool. Each file in the folder "migrations/versions"
is one change, with a function that makes it and one that takes it back.
Alembic keeps the id of the last file that ran in a table of its own,
"alembic_version", so a file never runs twice.

By hand, from the folder "backend", with the settings of the database:

    PYTHONPATH=src uv run --env-file .env python -m book_teller.migrate

A container does the same at its start: see start.py.
"""

import sys
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine

from book_teller.database import engine_from_environment
from book_teller.tables import Base

MIGRATIONS = Path(__file__).parent / "migrations"


def upgrade(engine: Engine) -> None:
    """Run every migration that did not run yet. Nothing to run: no change."""
    # One transaction for all of it. In PostgreSQL also CREATE TABLE and
    # ALTER TABLE can be taken back, so a migration that fails leaves nothing.
    with engine.begin() as connection:
        command.upgrade(_config(connection), "head")


def downgrade(engine: Engine) -> None:
    """Take every migration back, the last one first."""
    with engine.begin() as connection:
        command.downgrade(_config(connection), "base")


def differences(engine: Engine) -> list[object]:
    """What differs between the tables of the database and the ORM classes.

    Alembic's own comparison. An empty list: they say the same. It sees
    tables, columns, types, NULL or NOT NULL, indexes and foreign keys. It
    does not see a CHECK or a default.
    """
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return list(compare_metadata(context, Base.metadata))


def _config(connection: Connection) -> Config:
    """Alembic's settings, made here in place of the file alembic.ini.

    The connection is handed over, and migrations/env.py picks it up. So the
    migrations run on the connection of the caller.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.attributes["connection"] = connection
    return config


def main() -> int:
    engine = engine_from_environment()
    try:
        upgrade(engine)
    finally:
        engine.dispose()
    sys.stdout.write("The migrations ran: the tables are up to date.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
