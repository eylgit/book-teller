"""Tests of the settings of the database, and of the connection to it.

Most tests need nothing. Those that ask for "test_database" open a real
connection to the database of the tests: see conftest.py.
"""

import pytest
from sqlalchemy import Engine, event, text

from book_teller import database
from book_teller.database import TOKEN_AUDIENCE, make_engine
from book_teller.settings import (
    DatabaseSettings,
    SettingsError,
    read_database_settings,
)
from conftest import TEST_DATABASE

ENVIRONMENT = {
    "BOOK_TELLER_DATABASE_HOST": "db.example.invalid",
    "BOOK_TELLER_DATABASE_NAME": "book_teller",
    "BOOK_TELLER_DATABASE_USER": "the-app",
}


def test_the_settings_are_read_from_the_environment_variables() -> None:
    settings = read_database_settings(ENVIRONMENT)

    assert settings == DatabaseSettings(
        host="db.example.invalid", name="book_teller", user="the-app"
    )
    # Unless told, the login is the local one: no token of Azure.
    assert settings.azure_login is False
    assert settings.port == 5432


def test_the_azure_login_is_switched_on_by_its_setting() -> None:
    settings = read_database_settings(
        {**ENVIRONMENT, "BOOK_TELLER_DATABASE_LOGIN": "azure"}
    )

    assert settings.azure_login is True


def test_the_local_login_can_be_named_too() -> None:
    settings = read_database_settings(
        {**ENVIRONMENT, "BOOK_TELLER_DATABASE_LOGIN": "none"}
    )

    assert settings.azure_login is False


@pytest.mark.parametrize(
    "missing",
    [
        "BOOK_TELLER_DATABASE_HOST",
        "BOOK_TELLER_DATABASE_NAME",
        "BOOK_TELLER_DATABASE_USER",
    ],
)
def test_a_missing_setting_is_named_by_its_variable(missing: str) -> None:
    environment = {
        name: value for name, value in ENVIRONMENT.items() if name != missing
    }

    with pytest.raises(SettingsError, match=missing):
        read_database_settings(environment)


def test_a_login_that_is_neither_none_nor_azure_is_an_error() -> None:
    with pytest.raises(SettingsError, match="BOOK_TELLER_DATABASE_LOGIN"):
        read_database_settings(
            {**ENVIRONMENT, "BOOK_TELLER_DATABASE_LOGIN": "password"}
        )


def test_a_port_that_is_no_number_is_an_error() -> None:
    with pytest.raises(SettingsError, match="BOOK_TELLER_DATABASE_PORT"):
        read_database_settings(
            {**ENVIRONMENT, "BOOK_TELLER_DATABASE_PORT": "the usual"}
        )


def test_making_an_engine_opens_no_connection() -> None:
    # So the app can start while the database is down, or with a wrong
    # address: the first connection is opened when a statement needs it.
    asked: list[str] = []

    def token() -> str:
        asked.append("asked")
        return "a-fake-token"

    engine = make_engine(
        DatabaseSettings(
            host="no-such-host.invalid", name="x", user="y", azure_login=True
        ),
        token,
    )
    engine.dispose()

    assert asked == []


def test_the_azure_login_without_a_token_function_is_an_error() -> None:
    settings = DatabaseSettings(host="h", name="n", user="u", azure_login=True)

    with pytest.raises(SettingsError, match="token"):
        make_engine(settings)


def test_the_token_is_asked_for_the_postgresql_service_of_azure() -> None:
    # Azure checks that a token was made for the service that receives it.
    # This is the name of its database service for PostgreSQL.
    assert TOKEN_AUDIENCE == "https://ossrdbms-aad.database.windows.net/.default"


def _open_and_close(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1


def test_with_the_azure_login_each_new_connection_gets_a_fresh_token(
    test_database: None,
) -> None:
    # The local server takes no password, so it lets a connection in whatever
    # is sent as one. The test looks at what the code sends.
    tokens = iter(["token-1", "token-2", "token-3"])
    settings = DatabaseSettings(
        host=TEST_DATABASE.host,
        name=TEST_DATABASE.name,
        user=TEST_DATABASE.user,
        azure_login=True,
    )
    engine = make_engine(settings, lambda: next(tokens))
    sent: list[dict[str, object]] = []

    # "do_connect" is SQLAlchemy's moment just before a connection is opened.
    # This listener is added after the one of make_engine, so it runs after
    # it and sees what goes out.
    @event.listens_for(engine, "do_connect")
    def look(
        dialect: object,
        connection_record: object,
        arguments: list[object],
        parameters: dict[str, object],
    ) -> None:
        sent.append(dict(parameters))
        # The local server has no encryption, and Azure's has. Taken out
        # here, after it was seen, so that the connection can open.
        parameters.pop("sslmode", None)

    try:
        _open_and_close(engine)
        # The same connection is used again: no new token.
        _open_and_close(engine)
        # All open connections are closed. The next one is new.
        engine.dispose()
        _open_and_close(engine)
    finally:
        engine.dispose()

    assert [each["password"] for each in sent] == ["token-1", "token-2"]
    # On Azure the connection is always encrypted.
    assert [each["sslmode"] for each in sent] == ["require", "require"]


def test_with_the_local_login_no_password_goes_out(test_database: None) -> None:
    engine = make_engine(TEST_DATABASE)
    sent: list[dict[str, object]] = []

    @event.listens_for(engine, "do_connect")
    def look(
        dialect: object,
        connection_record: object,
        arguments: list[object],
        parameters: dict[str, object],
    ) -> None:
        sent.append(dict(parameters))

    try:
        _open_and_close(engine)
    finally:
        engine.dispose()

    assert len(sent) == 1
    assert not sent[0].get("password")


def test_with_the_local_login_a_token_function_is_never_asked(
    test_database: None,
) -> None:
    def token() -> str:
        raise AssertionError("the local login asks for no token")

    engine = make_engine(TEST_DATABASE, token)
    try:
        _open_and_close(engine)
    finally:
        engine.dispose()


# ---- The engine that the environment variables describe. ----
# It is what the app and tell.py use. These tests hold the join between the
# setting "the login is azure" and "a token goes out as the password".


def test_the_setting_azure_leads_to_a_token_as_the_password(
    test_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOOK_TELLER_DATABASE_HOST", TEST_DATABASE.host)
    monkeypatch.setenv("BOOK_TELLER_DATABASE_NAME", TEST_DATABASE.name)
    monkeypatch.setenv("BOOK_TELLER_DATABASE_USER", TEST_DATABASE.user)
    monkeypatch.setenv("BOOK_TELLER_DATABASE_LOGIN", "azure")
    # In the place of the real login to Azure: a token function that asks nobody.
    monkeypatch.setattr(
        database, "azure_database_login", lambda: lambda: "a-token-of-azure"
    )

    engine = database.engine_from_environment()
    sent: list[dict[str, object]] = []

    @event.listens_for(engine, "do_connect")
    def look(
        dialect: object,
        connection_record: object,
        arguments: list[object],
        parameters: dict[str, object],
    ) -> None:
        sent.append(dict(parameters))
        # As above: the local server has no encryption.
        parameters.pop("sslmode", None)

    try:
        _open_and_close(engine)
    finally:
        engine.dispose()

    assert [each["password"] for each in sent] == ["a-token-of-azure"]


def test_without_the_setting_azure_nobody_logs_in_to_azure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_login() -> None:
        raise AssertionError("the local login must not ask Azure")

    monkeypatch.setenv("BOOK_TELLER_DATABASE_HOST", "db.example.invalid")
    monkeypatch.setenv("BOOK_TELLER_DATABASE_NAME", "book_teller")
    monkeypatch.setenv("BOOK_TELLER_DATABASE_USER", "postgres")
    monkeypatch.delenv("BOOK_TELLER_DATABASE_LOGIN", raising=False)
    monkeypatch.setattr(database, "azure_database_login", no_login)

    # Making the engine opens no connection, so no database is needed.
    database.engine_from_environment().dispose()
