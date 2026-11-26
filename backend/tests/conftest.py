"""The database of the tests: a real PostgreSQL on this machine.

Start it before the tests, from the top folder of the repository:

    docker compose up --detach db

The tests use a database of their own, "book_teller_test", on that server.
So they never touch the database "book_teller", where the runs of the app
are. A test that needs the database fails without it; it does not skip.

pytest reads this file by itself. A test asks for a fixture by naming it as
an argument: "database" for the tables as the migrations make them,
"empty_database" for no tables at all.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from book_teller import migrate
from book_teller.database import make_engine
from book_teller.settings import DatabaseSettings

# The server of Docker Compose. It takes no password: see compose.yaml.
SERVER = DatabaseSettings(host="localhost", name="postgres", user="postgres")
TEST_DATABASE = DatabaseSettings(
    host="localhost", name="book_teller_test", user="postgres"
)


@pytest.fixture(scope="session")
def test_database() -> None:
    """Once for a test run: make the database of the tests if it is not there."""
    server = make_engine(SERVER)
    try:
        # CREATE DATABASE cannot run inside a transaction.
        with server.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE.name},
            )
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE.name}"'))
    finally:
        server.dispose()


@pytest.fixture
def empty_database(test_database: None) -> Iterator[Engine]:
    """For each test: the database of the tests, with nothing in it."""
    engine = make_engine(TEST_DATABASE)
    try:
        with engine.begin() as connection:
            # "public" is the schema that holds every table of ours.
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def database(empty_database: Engine) -> Engine:
    """For each test: the tables as the migrations make them, with no rows."""
    migrate.upgrade(empty_database)
    return empty_database
