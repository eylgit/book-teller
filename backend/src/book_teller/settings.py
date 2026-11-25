"""The settings of the model call. They come from environment variables.

Nothing here is read when the app starts. The settings are read when a model
is made, so the app runs without them as long as it calls no model.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass


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
