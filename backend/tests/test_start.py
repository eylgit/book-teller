"""Tests of the start of a container: the migrations, then the app.

No database and no server: the two steps are handed in as plain functions.
"""

import pytest

from book_teller.start import start


def test_without_a_database_the_app_starts_and_no_migration_runs() -> None:
    done: list[str] = []

    start(
        {},
        run_migrations=lambda: done.append("migrations"),
        serve=lambda: done.append("app"),
    )

    assert done == ["app"]


def test_an_empty_setting_counts_as_no_database() -> None:
    done: list[str] = []

    start(
        {"BOOK_TELLER_DATABASE_HOST": "  "},
        run_migrations=lambda: done.append("migrations"),
        serve=lambda: done.append("app"),
    )

    assert done == ["app"]


def test_with_a_database_the_migrations_run_before_the_app() -> None:
    done: list[str] = []

    start(
        {"BOOK_TELLER_DATABASE_HOST": "db"},
        run_migrations=lambda: done.append("migrations"),
        serve=lambda: done.append("app"),
    )

    assert done == ["migrations", "app"]


def test_when_the_migrations_fail_the_app_does_not_start() -> None:
    done: list[str] = []

    def fail() -> None:
        raise RuntimeError("the database is down")

    with pytest.raises(RuntimeError):
        start(
            {"BOOK_TELLER_DATABASE_HOST": "db"},
            run_migrations=fail,
            serve=lambda: done.append("app"),
        )

    assert done == []
