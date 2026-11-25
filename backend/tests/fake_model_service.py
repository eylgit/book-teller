"""A fake model service for the tests. It stands where the internet is.

Our code, LangChain and OpenAI's library all run for real. Only the last
step is replaced: the request never leaves the machine. The fake keeps each
request, so a test can read it, and gives back an answer that the test chose.

Nothing is replaced globally. The fake is handed in:

1. A test makes a FakeModelService with the answers it wants.
2. FakeModelService.client() builds an HTTP client whose transport, the part
   that would reach the network, is our own function _answer.
3. The test hands that client to make_model(..., http_client=...), which
   hands it to LangChain's model class, which hands it to OpenAI's library.
4. When the library sends a request, it lands in _answer.

The price: the answers below are written in the form of OpenAI's Responses
API. A change of the model's maker means writing them again.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx2


@dataclass
class Reply:
    """One answer of the service: a status, a body, and headers."""

    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


class FakeModelService:
    """Gives the replies in their order. The last one is given again and again.

    A reply can also be an error of the network, such as a timeout: it is
    raised, as the real network would raise it.
    """

    def __init__(self, *replies: Reply | Exception) -> None:
        self.requests: list[httpx2.Request] = []
        self._replies = list(replies)

    def client(self) -> httpx2.Client:
        """The HTTP client to hand to the model class."""
        return httpx2.Client(transport=httpx2.MockTransport(self._answer))

    def body(self, number: int = 0) -> dict[str, Any]:
        """The body of a request that was sent, as Python data."""
        body: dict[str, Any] = json.loads(self.requests[number].content)
        return body

    def _answer(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply = self._replies[0] if len(self._replies) == 1 else self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return httpx2.Response(reply.status, headers=reply.headers, json=reply.body)


# The library waits before it tries again. This header, which the real service
# can send too, tells it to wait one millisecond, so the tests stay fast.
TRY_AGAIN_AT_ONCE = {"retry-after-ms": "1"}


def answer(
    content: list[dict[str, Any]],
    status: str = "completed",
    incomplete_details: dict[str, str] | None = None,
) -> Reply:
    """An answer in the form of the Responses API, written by hand.

    The token counts are fixed: 1200 in, 800 out, and 650 of the 800 are
    thinking tokens.
    """
    return Reply(
        200,
        {
            "id": "resp_1",
            "object": "response",
            "created_at": 1,
            "status": status,
            "incomplete_details": incomplete_details,
            "error": None,
            "model": "gpt-5-mini-2025-08-07",
            "output": [
                {"id": "rs_1", "type": "reasoning", "summary": []},
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "status": status,
                    "content": content,
                },
            ],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 800,
                "total_tokens": 2000,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 650},
            },
        },
    )


def text_answer(text: str) -> Reply:
    """A finished answer whose text is the given string."""
    return answer([{"type": "output_text", "text": text, "annotations": []}])


def cut_off_answer(text: str) -> Reply:
    """An answer that stopped at a limit on output tokens, in the middle of its text."""
    return answer(
        [{"type": "output_text", "text": text, "annotations": []}],
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
    )


def cut_off_while_thinking() -> Reply:
    """An answer that reached the limit before the model wrote any text.

    The thinking used up all the tokens, so the answer holds no message.
    """
    reply = answer(
        [], status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    reply.body["output"] = [{"id": "rs_1", "type": "reasoning", "summary": []}]
    return reply


def refusal(words: str) -> Reply:
    """An answer in which the model says that it will not answer."""
    return answer([{"type": "refusal", "refusal": words}])


def error(status: int, message: str) -> Reply:
    """An error answer of the service, such as 429 "too many requests"."""
    return Reply(status, {"error": {"message": message}}, dict(TRY_AGAIN_AT_ONCE))
