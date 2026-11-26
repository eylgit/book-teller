"""The connection to the database. No password exists, here or on Azure.

SQLAlchemy's word for "how to reach one database" is an engine. It is made
once. It opens a connection when the first statement needs one, and keeps a
few open connections to use again (a pool).

Two logins, one code:

- On a developer's machine, the server of Docker Compose asks for no
  password.
- On Azure, the server takes only logins of Microsoft Entra. The app asks
  Azure for a token, as its managed identity, and sends it where a password
  would go. A token lives for a limited time, so a fresh one is asked for
  every new connection.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.pool import ConnectionPoolEntry

from book_teller.settings import (
    DatabaseSettings,
    SettingsError,
    read_database_settings,
)

# The login token is asked for this service: Azure's databases for
# PostgreSQL. Azure checks that a token was made for the service that
# receives it.
TOKEN_AUDIENCE = "https://ossrdbms-aad.database.windows.net/.default"


def azure_login() -> Callable[[], str]:
    """A function that fetches a login token for the database from Azure.

    On a developer's machine the login of the Azure CLI is used. In the cloud
    it is the managed identity of the app. The library keeps a token until
    shortly before it dies, so most calls ask nobody.
    """
    # Loaded here, not at the top: only a real connection to Azure needs it.
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    return lambda: credential.get_token(TOKEN_AUDIENCE).token


def make_engine(
    settings: DatabaseSettings, token_function: Callable[[], str] | None = None
) -> Engine:
    """Make the engine. This opens no connection yet.

    With the Azure login, the token function is asked before each new
    connection. With the local login it is never asked.
    """
    # "postgresql+psycopg": the database, and the driver that speaks to it.
    url = URL.create(
        "postgresql+psycopg",
        username=settings.user,
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )
    # "pool_pre_ping": before a kept connection is used again, the engine
    # asks whether it is still alive, and opens a new one if it is not.
    engine = create_engine(url, pool_pre_ping=True)
    if not settings.azure_login:
        return engine
    if token_function is None:
        raise SettingsError("The Azure login of the database needs a token function.")
    fetch_token = token_function

    # "do_connect" is SQLAlchemy's moment just before a connection is opened.
    # It is the way that SQLAlchemy names for a password that changes.
    @event.listens_for(engine, "do_connect")
    def hand_over_a_fresh_token(
        dialect: Dialect,
        connection_record: ConnectionPoolEntry,
        arguments: list[Any],
        parameters: dict[str, Any],
    ) -> None:
        parameters["password"] = fetch_token()
        # The token travels over the internet: only on an encrypted connection.
        parameters["sslmode"] = "require"

    return engine


def engine_from_environment() -> Engine:
    """The engine that the environment variables describe.

    Raises SettingsError when a setting is missing.
    """
    settings = read_database_settings()
    return make_engine(settings, azure_login() if settings.azure_login else None)
