"""Tests of the migrations: the files that make and change the tables.

They run the real migrations on a real PostgreSQL: see conftest.py. The
statements here are plain SQL, so they test the tables themselves, not the
code that uses them.
"""

import re

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from book_teller import migrate
from book_teller.check_step import Kind
from book_teller.tables import Status

INSERT_FAULT = text(
    "INSERT INTO faults (run_id, position, sentence, kind, paragraph, quote,"
    " reason, found_in, sentence_exists)"
    " VALUES (:run_id, :position, 1, :kind, 1, 'a quote', 'a reason', 1, true)"
)


def tables_of(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def insert_run(connection: Connection, status: str = "waiting") -> int:
    number = connection.execute(
        text(
            "INSERT INTO runs (status, chapter)"
            " VALUES (:status, 'A chapter.') RETURNING id"
        ),
        {"status": status},
    ).scalar_one()
    assert isinstance(number, int)
    return number


def allowed_values(engine: Engine, table: str, column: str) -> set[str]:
    """The values that the CHECK of a column lets in, read from the database."""
    with engine.connect() as connection:
        definitions = connection.scalars(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conrelid = to_regclass(:table) AND contype = 'c'"
            ),
            {"table": table},
        ).all()
    # PostgreSQL prints a CHECK like this:
    # CHECK ((status = ANY (ARRAY['waiting'::text, 'writing'::text])))
    [definition] = [each for each in definitions if column in each]
    return set(re.findall(r"'([a-z_]+)'", definition))


def test_the_migrations_make_the_two_tables(empty_database: Engine) -> None:
    assert tables_of(empty_database) == set()

    migrate.upgrade(empty_database)

    # The third table is Alembic's own: it holds which migration ran last.
    assert tables_of(empty_database) == {"runs", "faults", "alembic_version"}


def test_the_migrations_can_be_taken_back(database: Engine) -> None:
    migrate.downgrade(database)

    assert tables_of(database) == {"alembic_version"}


def test_the_migrations_can_run_again_after_they_were_taken_back(
    database: Engine,
) -> None:
    migrate.downgrade(database)
    migrate.upgrade(database)

    assert tables_of(database) == {"runs", "faults", "alembic_version"}


def test_a_second_upgrade_changes_nothing(database: Engine) -> None:
    # A container runs the migrations at each start.
    with database.begin() as connection:
        number = insert_run(connection)

    migrate.upgrade(database)

    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM runs")) == 1
        assert connection.scalar(text("SELECT id FROM runs")) == number


def test_the_tables_are_what_the_orm_classes_say(database: Engine) -> None:
    # Alembic compares the tables of the database with the classes of
    # tables.py. A column that is in only one of the two shows here.
    assert migrate.differences(database) == []


def test_a_new_run_gets_its_defaults_from_the_database(database: Engine) -> None:
    with database.begin() as connection:
        connection.execute(text("INSERT INTO runs (chapter) VALUES ('A chapter.')"))
        row = connection.execute(text("SELECT * FROM runs")).mappings().one()

    assert row["id"] >= 1
    assert row["status"] == "waiting"
    assert row["script"] is None
    assert row["failure"] is None
    assert (row["tokens_in"], row["tokens_out"], row["thinking_tokens"]) == (0, 0, 0)
    assert row["model_seconds"] == 0
    # With a time zone: one moment, not a time on some clock.
    assert row["created_at"].tzinfo is not None
    assert row["finished_at"] is None


def test_the_database_refuses_a_status_that_is_not_in_the_list(
    database: Engine,
) -> None:
    with pytest.raises(IntegrityError), database.begin() as connection:
        insert_run(connection, status="sleeping")


def test_the_database_refuses_a_kind_that_is_not_in_the_list(database: Engine) -> None:
    with database.begin() as connection:
        run_id = insert_run(connection)

    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            INSERT_FAULT, {"run_id": run_id, "position": 1, "kind": "boring"}
        )


def test_the_database_refuses_a_fault_of_a_run_that_does_not_exist(
    database: Engine,
) -> None:
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            INSERT_FAULT, {"run_id": 999, "position": 1, "kind": "wrong_fact"}
        )


def test_the_statuses_of_the_database_are_the_statuses_of_the_code(
    database: Engine,
) -> None:
    in_the_code = {status.value for status in Status}

    assert allowed_values(database, "runs", "status") == in_the_code


def test_the_kinds_of_the_database_are_the_kinds_of_the_checker(
    database: Engine,
) -> None:
    in_the_code = {kind.value for kind in Kind}

    assert allowed_values(database, "faults", "kind") == in_the_code


def test_two_faults_of_one_run_cannot_have_the_same_position(database: Engine) -> None:
    with database.begin() as connection:
        run_id = insert_run(connection)
        connection.execute(
            INSERT_FAULT, {"run_id": run_id, "position": 1, "kind": "wrong_fact"}
        )

    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            INSERT_FAULT, {"run_id": run_id, "position": 1, "kind": "left_out"}
        )


def test_deleting_a_run_deletes_its_faults(database: Engine) -> None:
    with database.begin() as connection:
        kept = insert_run(connection)
        deleted = insert_run(connection)
        for run_id in (kept, deleted):
            connection.execute(
                INSERT_FAULT, {"run_id": run_id, "position": 1, "kind": "wrong_fact"}
            )

    with database.begin() as connection:
        connection.execute(text("DELETE FROM runs WHERE id = :id"), {"id": deleted})

    with database.connect() as connection:
        left = connection.scalars(text("SELECT run_id FROM faults")).all()
    assert left == [kept]
