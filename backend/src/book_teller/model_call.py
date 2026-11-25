"""The model call. Every call of the app to the model goes through this file.

LangChain's model class has defaults that hide choices. This file names each
one: which API, the strict shape, the thinking setting, the timeout, and the
number of tries.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

import httpx2
import openai
from langchain_core.exceptions import ModelRefusalError
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from book_teller.settings import ModelSettings

# After a first try that fails with "too many requests", a timeout or an error
# of the service, the library tries again this many times, with a growing wait.
# So one call makes at most three requests. Two is also what the library does
# by itself today; it is written out so that the number is in plain sight.
RETRIES = 2

# The login token is asked for this service. Azure checks that a token was
# made for the service that receives it.
TOKEN_AUDIENCE = "https://cognitiveservices.azure.com/.default"


class Reason(StrEnum):
    """Why a model call failed."""

    TIMEOUT = "timeout"
    TOO_MANY_REQUESTS = "too many requests"
    NO_PERMISSION = "no permission"
    REFUSED = "refused"
    WRONG_SHAPE = "wrong shape"
    SERVICE_ERROR = "service error"


class ModelCallError(Exception):
    """The one error of a model call. It holds the reason and the library's words."""

    def __init__(self, reason: Reason, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


@dataclass(frozen=True)
class ModelAnswer[Shape]:
    """A good answer: the object in the named shape, and what the call cost."""

    parsed: Shape
    tokens_in: int
    # The answer and the thinking together. Both are billed as output.
    tokens_out: int
    # The part of tokens_out that was thinking.
    thinking_tokens: int
    seconds: float


def azure_login() -> Callable[[], str]:
    """A function that fetches a fresh login token from Azure. No key exists.

    On a developer's machine the login of the Azure CLI is used. In the cloud
    it is the managed identity of the app.
    """
    # Loaded here, not at the top: only a real call needs this library.
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    return get_bearer_token_provider(DefaultAzureCredential(), TOKEN_AUDIENCE)


def make_model(
    settings: ModelSettings,
    token_function: Callable[[], str],
    http_client: httpx2.Client | None = None,
) -> ChatOpenAI:
    """Build LangChain's model class, with every choice written out.

    The token function is handed over itself, not one token from it: a token
    dies after about an hour, and the library asks for one on every request.
    The tests hand in an HTTP client that never reaches the network.
    """
    return ChatOpenAI(
        model=settings.deployment,
        base_url=settings.endpoint,
        api_key=token_function,
        # The newer of OpenAI's two APIs. The class would move to it by itself
        # because of the thinking setting below. Here the code says so.
        use_responses_api=True,
        reasoning={"effort": settings.thinking},
        # The Responses API keeps every request and its answer at the service
        # unless the request says no. We send one request and never ask for
        # an old answer again, so nothing needs to be kept there.
        store=False,
        timeout=settings.timeout_seconds,
        max_retries=RETRIES,
        http_client=http_client,
    )


def ask_model[Shape: BaseModel](
    model: ChatOpenAI, instructions: str, text: str, shape: type[Shape]
) -> ModelAnswer[Shape]:
    """Send the instructions and the text. Return the answer in the named shape.

    Raises ModelCallError, with its reason, whenever no good answer came.
    """
    # "json_schema" with "strict": the service itself forces the shape. The
    # class does the same by itself today for a Pydantic shape. Both are
    # written out, so that a test fails if a later version changes its mind.
    # "include_raw": the token counts come back beside the parsed answer.
    asker = model.with_structured_output(
        shape, method="json_schema", strict=True, include_raw=True
    )
    started = time.monotonic()
    try:
        result = cast(
            dict[str, Any],
            asker.invoke([("system", instructions), ("user", text)]),
        )
    except ValidationError as error:
        # Also an answer that was cut off at a limit on output tokens ends
        # here, as "Invalid JSON": bug report 41688 of langchain-openai. See
        # the test of that case.
        raise ModelCallError(Reason.WRONG_SHAPE, str(error)) from error
    except openai.APITimeoutError as error:
        raise ModelCallError(Reason.TIMEOUT, str(error)) from error
    except openai.RateLimitError as error:
        raise ModelCallError(Reason.TOO_MANY_REQUESTS, str(error)) from error
    except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
        raise ModelCallError(Reason.NO_PERMISSION, str(error)) from error
    except Exception as error:
        # Everything else: an error of the service, a network that is down, an
        # answer that the service marks as failed, a login that did not work.
        raise ModelCallError(Reason.SERVICE_ERROR, str(error)) from error
    seconds = time.monotonic() - started

    problem = result["parsing_error"]
    if isinstance(problem, ModelRefusalError):
        raise ModelCallError(Reason.REFUSED, str(problem)) from problem
    parsed = result["parsed"]
    if not isinstance(parsed, shape):
        raise ModelCallError(Reason.WRONG_SHAPE, str(problem)) from problem

    usage = result["raw"].usage_metadata or {}
    return ModelAnswer(
        parsed=parsed,
        tokens_in=usage.get("input_tokens", 0),
        tokens_out=usage.get("output_tokens", 0),
        thinking_tokens=usage.get("output_token_details", {}).get("reasoning", 0),
        seconds=seconds,
    )
