"""The settings of the model call, of the database and of a run. They come
from environment variables.

Nothing here is read when this file is loaded. The settings of the model are
read when a model is made, and those of the database when a connection is
set up. So the app runs without the first as long as it calls no model, and
without the second as long as it has no database.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class SettingsError(Exception):
    """A setting is missing or cannot be used. The message names its variable."""


@dataclass(frozen=True)
class ModelSettings:
    """What one model call needs to know."""

    # The address of the model service. It ends with "/openai/v1/".
    endpoint: str
    # The name that the model has in the Azure resource.
    deployment: str
    # How long the model thinks before it answers, e.g. "minimal", "low" or
    # "medium".
    # More thinking costs more tokens and more seconds.
    thinking: str = "low"
    # One try gives up after so many seconds. A call is tried three times.
    # Measured on 2026-11-25: "low" took about 15 seconds, "medium" about 39.
    timeout_seconds: float = 60


def read_model_settings(environment: Mapping[str, str] | None = None) -> ModelSettings:
    """Read the settings from the environment variables, or from the given ones."""
    if environment is None:
        environment = os.environ
    return ModelSettings(
        endpoint=_needed(environment, "BOOK_TELLER_MODEL_ENDPOINT"),
        deployment=_needed(environment, "BOOK_TELLER_MODEL_DEPLOYMENT"),
        thinking=environment.get("BOOK_TELLER_MODEL_THINKING", "").strip()
        or ModelSettings.thinking,
        timeout_seconds=_number(
            environment,
            "BOOK_TELLER_MODEL_TIMEOUT_SECONDS",
            ModelSettings.timeout_seconds,
        ),
    )


def _needed(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise SettingsError(f"The environment variable {name} is not set.")
    return value


def _number(environment: Mapping[str, str], name: str, default: float) -> float:
    value = environment.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        raise SettingsError(
            f"The environment variable {name} must be a number, not {value!r}."
        ) from None


@dataclass(frozen=True)
class DatabaseSettings:
    """What a connection to the database needs to know. None of it is a secret."""

    # The address of the database server.
    host: str
    # The name of the database on that server.
    name: str
    # The name of the login. On Azure: the name of the app's managed identity.
    user: str
    # False: the local server of Docker Compose, which asks for no password.
    # True: Azure. A fresh token of Microsoft Entra goes where a password
    # would go, and the connection is encrypted.
    azure_login: bool = False
    port: int = 5432


def read_database_settings(
    environment: Mapping[str, str] | None = None,
) -> DatabaseSettings:
    """Read the settings from the environment variables, or from the given ones."""
    if environment is None:
        environment = os.environ
    return DatabaseSettings(
        host=_needed(environment, "BOOK_TELLER_DATABASE_HOST"),
        name=_needed(environment, "BOOK_TELLER_DATABASE_NAME"),
        user=_needed(environment, "BOOK_TELLER_DATABASE_USER"),
        azure_login=_azure_login(environment, "BOOK_TELLER_DATABASE_LOGIN"),
        port=_whole_number(
            environment, "BOOK_TELLER_DATABASE_PORT", DatabaseSettings.port
        ),
    )


def _azure_login(environment: Mapping[str, str], name: str) -> bool:
    value = environment.get(name, "").strip() or "none"
    if value not in ("none", "azure"):
        raise SettingsError(
            f"The environment variable {name} must be none or azure, not {value!r}."
        )
    return value == "azure"


def _whole_number(environment: Mapping[str, str], name: str, default: int) -> int:
    value = environment.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise SettingsError(
            f"The environment variable {name} must be a whole number, not {value!r}."
        ) from None


@dataclass(frozen=True)
class RunSettings:
    """Who may start a run, and how many runs a day may start."""

    # The owner's key: a long random text that stands in for a login. Only a
    # request that sends it may start a run or read one. None: no key is set
    # up, and then nobody may. It is the one secret among the settings.
    # "repr=False": printing the settings does not show the key.
    owner_key: str | None = field(default=None, repr=False)
    # The cap of the day: so many runs may start on one day of the clock UTC.
    runs_a_day: int = 20


def read_run_settings(environment: Mapping[str, str] | None = None) -> RunSettings:
    """Read the settings from the environment variables, or from the given ones."""
    if environment is None:
        environment = os.environ
    name = "BOOK_TELLER_RUNS_A_DAY"
    runs_a_day = _whole_number(environment, name, RunSettings.runs_a_day)
    if runs_a_day < 0:
        raise SettingsError(
            f"The environment variable {name} must be 0 or more, not {runs_a_day}."
        )
    return RunSettings(
        # A key of only spaces is no key. An empty key would be "right" for
        # a request that sends an empty key.
        owner_key=environment.get("BOOK_TELLER_OWNER_KEY", "").strip() or None,
        runs_a_day=runs_a_day,
    )
