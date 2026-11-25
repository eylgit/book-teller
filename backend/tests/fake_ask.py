"""A fake "ask the model" for the tests of the graph. No model and no HTTP.

The graph does not know the model. It is handed one function, "ask", and
calls it in each step. The real one is ask_model of model_call.py. A test
hands in a FakeAsk instead:

    ask = FakeAsk()
    build_graph(ask).invoke({"chapter": "..."})

The fake keeps what it was asked, so a test can read it, and gives a fixed
answer for each shape: a script for the writer, flags for the checker.
"""

from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel

from book_teller.check_step import Flag, Flags, Kind
from book_teller.model_call import ModelAnswer, ModelCallError
from book_teller.write_step import Script

SCRIPT = Script(sentences=["James starts with the word habit.", "Habits can be good."])

FLAGS = Flags(
    flags=[
        Flag(
            sentence=2,
            kind=Kind.WRONG_STRENGTH,
            paragraph=1,
            quote="in most cases",
            reason="The script says always.",
        )
    ]
)

# What each fake call "cost": tokens in, tokens out, thinking tokens, seconds.
COST_OF = {Script: (100, 50, 10, 1.5), Flags: (200, 80, 60, 2.5)}


@dataclass(frozen=True)
class Asked:
    """One call that the fake received."""

    instructions: str
    text: str
    shape: type[BaseModel]


class FakeAsk:
    """Stands where ask_model stands.

    fail_once: for a shape, the error of its first call; the next call answers.
    fail_always: for a shape, the error of every call.
    """

    def __init__(
        self,
        fail_once: dict[type[BaseModel], ModelCallError] | None = None,
        fail_always: dict[type[BaseModel], ModelCallError] | None = None,
    ) -> None:
        self.asked: list[Asked] = []
        self._fail_once = dict(fail_once or {})
        self._fail_always = dict(fail_always or {})
        self._answers: dict[type[BaseModel], BaseModel] = {Script: SCRIPT, Flags: FLAGS}

    def __call__[Shape: BaseModel](
        self, instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        self.asked.append(Asked(instructions, text, shape))
        if shape in self._fail_always:
            raise self._fail_always[shape]
        if shape in self._fail_once:
            raise self._fail_once.pop(shape)
        tokens_in, tokens_out, thinking_tokens, seconds = COST_OF[shape]
        return ModelAnswer(
            parsed=cast(Shape, self._answers[shape]),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            thinking_tokens=thinking_tokens,
            seconds=seconds,
        )

    def shapes(self) -> list[type[BaseModel]]:
        """The shapes that were asked for, in the order of the calls."""
        return [asked.shape for asked in self.asked]
