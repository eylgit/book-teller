"""Alembic runs this file each time it works with the migrations.

It tells Alembic two things: which connection to use, and where the ORM
classes are, so that Alembic can compare them with the tables.
"""

from alembic import context
from sqlalchemy import Connection

from book_teller.database import engine_from_environment
from book_teller.tables import Base


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


# migrate.py hands its own connection over. The command "alembic" does not:
# then the connection is made from the environment variables.
handed_over = context.config.attributes.get("connection")
if handed_over is not None:
    _run(handed_over)
else:
    engine = engine_from_environment()
    try:
        with engine.connect() as connection:
            _run(connection)
    finally:
        engine.dispose()
