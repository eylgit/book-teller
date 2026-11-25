"""Tests of the model call.

No test here reaches the network or costs money. A fake model service stands
where the internet is: see fake_model_service.py.
"""

import httpx2
import pytest
from pydantic import BaseModel

from book_teller.model_call import ModelCallError, Reason, ask_model, make_model
from book_teller.settings import ModelSettings, SettingsError, read_model_settings
from fake_model_service import (
    FakeModelService,
    Reply,
    answer,
    cut_off_answer,
    cut_off_while_thinking,
    error,
    refusal,
    text_answer,
)


class Summary(BaseModel):
    """The shape that these tests ask for. Any shape would do."""

    title: str
    points: list[str]


SETTINGS = ModelSettings(
    endpoint="https://example.invalid/openai/v1/",
    deployment="my-deployment",
    thinking="medium",
    timeout_seconds=5,
)

GOOD = text_answer('{"title": "Whales", "points": ["They sing.", "They dive."]}')


def fake_token() -> str:
    return "a-fake-token"


def ask(service: FakeModelService) -> Summary:
    """One call through the fake service, with fixed instructions and text."""
    model = make_model(SETTINGS, fake_token, http_client=service.client())
    return ask_model(model, "THE INSTRUCTIONS", "THE TEXT", Summary).parsed


def reason_of(service: FakeModelService) -> Reason:
    """The reason of the error that one call through this service ends in."""
    with pytest.raises(ModelCallError) as caught:
        ask(service)
    return caught.value.reason


# ------------------------------------------------- the request that is sent


def test_the_request_goes_to_the_responses_address() -> None:
    service = FakeModelService(GOOD)
    ask(service)

    assert str(service.requests[0].url) == "https://example.invalid/openai/v1/responses"


def test_the_request_asks_for_the_strict_shape() -> None:
    service = FakeModelService(GOOD)
    ask(service)

    shape = service.body()["text"]["format"]
    assert shape["type"] == "json_schema"
    assert shape["strict"] is True
    assert set(shape["schema"]["properties"]) == {"title", "points"}


def test_the_request_holds_the_thinking_setting() -> None:
    service = FakeModelService(GOOD)
    ask(service)

    assert service.body()["reasoning"] == {"effort": "medium"}


def test_the_request_carries_the_timeout_from_the_settings() -> None:
    # Without it, the library would wait ten minutes for one try.
    service = FakeModelService(GOOD)
    ask(service)

    assert service.requests[0].extensions["timeout"]["read"] == 5


def test_the_request_sets_no_cap_on_output_tokens() -> None:
    # No cap of our own. The timeout and the limit on the pasted text guard
    # the cost. An answer can still be cut off, at the model's own limit: the
    # tests further down hold that such an answer is an error.
    service = FakeModelService(GOOD)
    ask(service)

    assert "max_output_tokens" not in service.body()


def test_the_request_tells_the_service_not_to_keep_the_answer() -> None:
    # The Responses API keeps every request and its answer at the service,
    # unless the request says no. Seen in the first real answer: "store": true.
    service = FakeModelService(GOOD)
    ask(service)

    assert service.body()["store"] is False


def test_the_request_holds_the_deployment_the_instructions_and_the_text() -> None:
    service = FakeModelService(GOOD)
    ask(service)

    body = service.body()
    assert body["model"] == "my-deployment"
    assert [(part["role"], part["content"]) for part in body["input"]] == [
        ("system", "THE INSTRUCTIONS"),
        ("user", "THE TEXT"),
    ]


def test_the_token_is_asked_for_again_on_every_request() -> None:
    # A login token dies after about an hour. So the model class must get the
    # function that fetches one, and never one token that was fetched once.
    tokens: list[str] = []

    def numbered_token() -> str:
        tokens.append(f"token-{len(tokens) + 1}")
        return tokens[-1]

    service = FakeModelService(GOOD)
    model = make_model(SETTINGS, numbered_token, http_client=service.client())
    ask_model(model, "THE INSTRUCTIONS", "THE TEXT", Summary)
    ask_model(model, "THE INSTRUCTIONS", "THE TEXT", Summary)

    sent = [request.headers["authorization"] for request in service.requests]
    assert sent == ["Bearer token-1", "Bearer token-2"]


# ------------------------------------------------------------ a good answer


def test_a_good_answer_comes_back_in_the_shape_with_its_counts() -> None:
    service = FakeModelService(GOOD)
    model = make_model(SETTINGS, fake_token, http_client=service.client())

    result = ask_model(model, "THE INSTRUCTIONS", "THE TEXT", Summary)

    assert result.parsed == Summary(title="Whales", points=["They sing.", "They dive."])
    assert result.tokens_in == 1200
    assert result.tokens_out == 800
    assert result.thinking_tokens == 650
    assert result.seconds >= 0


# ------------------------------------------------ an answer that is no good


def test_an_answer_that_was_cut_off_is_a_wrong_shape() -> None:
    # A known bug of langchain-openai, report 41688, open on 2026-11-25:
    # https://github.com/langchain-ai/langchain/issues/41688
    # An answer that stops at a limit on output tokens is half a JSON text.
    # The library does not say "cut off". It reads the half text as JSON and
    # fails with "Invalid JSON". We do not code around the bug: the call fails
    # either way, and the words of the library stay in our error.
    # So: "wrong shape" with "Invalid JSON: EOF" means, most likely, that the
    # answer was cut off. Lower the thinking setting, or send a shorter text.
    # When this test fails one day, the bug is probably fixed: read the report.
    half_an_answer = '{"title": "Whales", "points": ["They si'
    service = FakeModelService(cut_off_answer(half_an_answer))

    with pytest.raises(ModelCallError) as caught:
        ask(service)

    assert caught.value.reason is Reason.WRONG_SHAPE
    assert "Invalid JSON" in str(caught.value)


def test_an_answer_cut_off_while_the_model_was_thinking_is_a_wrong_shape() -> None:
    # The second way to be cut off: the thinking uses up the whole limit, and
    # the answer holds no text at all. The library then says that the answer
    # has no "parsed" field. The words "incomplete" and "max_output_tokens"
    # are in its message, so the cause can be read there.
    service = FakeModelService(cut_off_while_thinking())

    with pytest.raises(ModelCallError) as caught:
        ask(service)

    assert caught.value.reason is Reason.WRONG_SHAPE
    assert "does not have a 'parsed' field" in str(caught.value)
    assert "incomplete" in str(caught.value)
    assert "max_output_tokens" in str(caught.value)


def test_json_that_is_not_in_the_shape_is_a_wrong_shape() -> None:
    service = FakeModelService(text_answer('{"title": "Whales"}'))

    assert reason_of(service) is Reason.WRONG_SHAPE


def test_a_refusal_of_the_model_is_refused() -> None:
    service = FakeModelService(refusal("I cannot help with that."))

    with pytest.raises(ModelCallError) as caught:
        ask(service)

    assert caught.value.reason is Reason.REFUSED
    assert "I cannot help with that." in str(caught.value)


# ----------------------------------------------------- a call that fails


def test_too_many_requests_every_time_gives_up_after_three_requests() -> None:
    service = FakeModelService(error(429, "Too many requests"))

    assert reason_of(service) is Reason.TOO_MANY_REQUESTS
    assert len(service.requests) == 3


def test_too_many_requests_once_and_then_a_good_answer() -> None:
    service = FakeModelService(error(429, "Too many requests"), GOOD)

    assert ask(service).title == "Whales"
    assert len(service.requests) == 2


def test_no_answer_in_time_is_a_timeout() -> None:
    # Slow on purpose, a second or two: the library waits before each new
    # try, and the network gave it no header that says how long.
    service = FakeModelService(httpx2.ReadTimeout("no answer in time"))

    assert reason_of(service) is Reason.TIMEOUT
    assert len(service.requests) == 3


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_login_is_no_permission_and_is_not_tried_again(status: int) -> None:
    service = FakeModelService(error(status, "Not allowed"))

    assert reason_of(service) is Reason.NO_PERMISSION
    assert len(service.requests) == 1


def test_an_error_of_the_service_is_a_service_error() -> None:
    service = FakeModelService(error(500, "Something broke"))

    assert reason_of(service) is Reason.SERVICE_ERROR
    assert len(service.requests) == 3


def test_a_request_that_the_service_does_not_accept_is_a_service_error() -> None:
    # For example a thinking setting that the model does not know.
    service = FakeModelService(Reply(400, {"error": {"message": "Unsupported value"}}))

    with pytest.raises(ModelCallError) as caught:
        ask(service)

    assert caught.value.reason is Reason.SERVICE_ERROR
    assert "Unsupported value" in str(caught.value)
    assert len(service.requests) == 1


def test_an_answer_that_the_service_marks_as_failed_is_a_service_error() -> None:
    # The service can answer "200 OK" and still say inside that it failed.
    # The library raises a plain error for it, not one of its own kinds.
    reply = answer([], status="failed")
    reply.body["output"] = []
    reply.body["error"] = {"code": "server_error", "message": "The model failed."}
    service = FakeModelService(reply)

    with pytest.raises(ModelCallError) as caught:
        ask(service)

    assert caught.value.reason is Reason.SERVICE_ERROR
    assert "server_error" in str(caught.value)


def test_a_login_that_fails_is_a_service_error() -> None:
    # For example: the login of the Azure CLI has run out.
    def no_token() -> str:
        raise RuntimeError("Please run 'az login'.")

    service = FakeModelService(GOOD)
    model = make_model(SETTINGS, no_token, http_client=service.client())

    with pytest.raises(ModelCallError) as caught:
        ask_model(model, "THE INSTRUCTIONS", "THE TEXT", Summary)

    assert caught.value.reason is Reason.SERVICE_ERROR
    assert "az login" in str(caught.value)
    assert service.requests == []


# ------------------------------------------------------------- the settings


def test_the_settings_are_read_from_the_environment() -> None:
    settings = read_model_settings(
        {
            "BOOK_TELLER_MODEL_ENDPOINT": "https://example.invalid/openai/v1/",
            "BOOK_TELLER_MODEL_DEPLOYMENT": "my-deployment",
            "BOOK_TELLER_MODEL_THINKING": "medium",
            "BOOK_TELLER_MODEL_TIMEOUT_SECONDS": "30",
        }
    )

    assert settings == ModelSettings(
        endpoint="https://example.invalid/openai/v1/",
        deployment="my-deployment",
        thinking="medium",
        timeout_seconds=30,
    )


def test_a_setting_that_is_left_out_or_left_empty_gets_its_default() -> None:
    settings = read_model_settings(
        {
            "BOOK_TELLER_MODEL_ENDPOINT": "https://example.invalid/openai/v1/",
            "BOOK_TELLER_MODEL_DEPLOYMENT": "my-deployment",
            "BOOK_TELLER_MODEL_THINKING": " ",
        }
    )

    assert settings.thinking == "low"
    # About four times what one call with "low" took when it was measured.
    assert settings.timeout_seconds == 60


@pytest.mark.parametrize(
    "missing", ["BOOK_TELLER_MODEL_ENDPOINT", "BOOK_TELLER_MODEL_DEPLOYMENT"]
)
def test_a_missing_setting_is_named(missing: str) -> None:
    environment = {
        "BOOK_TELLER_MODEL_ENDPOINT": "https://example.invalid/openai/v1/",
        "BOOK_TELLER_MODEL_DEPLOYMENT": "my-deployment",
    }
    del environment[missing]

    with pytest.raises(SettingsError, match=missing):
        read_model_settings(environment)


def test_a_setting_that_is_not_a_number_is_named() -> None:
    environment = {
        "BOOK_TELLER_MODEL_ENDPOINT": "https://example.invalid/openai/v1/",
        "BOOK_TELLER_MODEL_DEPLOYMENT": "my-deployment",
        "BOOK_TELLER_MODEL_TIMEOUT_SECONDS": "soon",
    }

    with pytest.raises(SettingsError, match="BOOK_TELLER_MODEL_TIMEOUT_SECONDS"):
        read_model_settings(environment)
