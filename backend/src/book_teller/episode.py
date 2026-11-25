"""The graph of an episode: three steps in a fixed order.

write: the model tells the chapter as a script. check: the model looks for
faults in the script. guard: plain code checks each fault that the checker
reported. Only the first two ask the model.

LangGraph runs the steps and carries the data from one to the next. Its
words, as this file uses them:

- state: the data that all steps share. Here: EpisodeState.
- node: one step, a plain function. It gets the state and returns only the
  part that it changes.
- edge: an arrow that says which node runs next.
- reducer: the rule for how a node's result goes into the state.
- retry policy: the rule for when a failed node runs again.

Nothing is saved between the steps: the graph has no checkpointer. When a
run fails, it starts again from the first step.
"""

import operator
from dataclasses import dataclass
from typing import Annotated, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy
from pydantic import BaseModel

from book_teller import check_step, guard, write_step
from book_teller.model_call import ModelAnswer, ModelCallError, Reason


class Ask(Protocol):
    """ "Ask the model": the one function that the steps need.

    The graph does not know the model. It is handed this function. The real
    one is ask_model of model_call.py, with the model already inside. A test
    hands in a function that gives fixed answers.
    """

    def __call__[Shape: BaseModel](
        self, instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]: ...


@dataclass(frozen=True)
class Cost:
    """What the model call of one step cost.

    Only a call that answered has a line. A try that failed is not counted:
    the model call raises before it gives the token counts.
    """

    step: str
    tokens_in: int
    tokens_out: int
    thinking_tokens: int
    seconds: float


class EpisodeState(TypedDict, total=False):
    """The state: what the three steps share.

    "total=False": a key may be missing. At the start only the chapter is
    there, and each step returns only the keys that it changes.
    """

    chapter: str
    # The script, sentence by sentence. Written by the step "write".
    script: list[str]
    # The faults that the checker found. Written by the step "check".
    flags: list[check_step.Flag]
    # The same faults, each with the answer of the guard: proven, or what is
    # wrong with it. Written by the step "guard". "flags" stays as it came.
    checked: list[guard.CheckedFlag]
    # One line for each model call. "operator.add" is the reducer of this
    # key: a step's list is added to the list that is there. Without it the
    # second step would replace the line of the first, as happens for every
    # other key.
    costs: Annotated[list[Cost], operator.add]


# A second try can mend these. It cannot mend "no permission", "refused" or
# "wrong shape": the next try would end the same way.
# "service error" is wide: model_call.py gives it to everything else that goes
# wrong. So it also holds a request that the service does not accept, and a
# login that did not work. Those get a second try too, for nothing.
WORTH_A_SECOND_TRY = frozenset(
    {Reason.TIMEOUT, Reason.TOO_MANY_REQUESTS, Reason.SERVICE_ERROR}
)


def worth_a_second_try(error: Exception) -> bool:
    """Our answer to LangGraph's question: run the failed node again?

    LangGraph's own answer is yes for every ModelCallError, so also for a
    refused login.
    """
    return isinstance(error, ModelCallError) and error.reason in WORTH_A_SECOND_TRY


# The retry policy of the two nodes that ask the model. "max_attempts"
# counts the first try, so a failed node runs once more. The model call makes
# up to three requests by itself (RETRIES in model_call.py), so one step can
# make up to six.
RETRY = RetryPolicy(max_attempts=2, retry_on=worth_a_second_try)

type EpisodeGraph = CompiledStateGraph[EpisodeState, None, EpisodeState, EpisodeState]


def build_graph(ask: Ask, retry: RetryPolicy = RETRY) -> EpisodeGraph:
    """Put the graph together: START -> write -> check -> guard -> END.

    run_episode below runs it: "invoke" starts at START with the chapter, and
    its answer is the last state. A step that fails for good ends the run: its
    ModelCallError leaves "invoke" as it is.
    """

    def write(state: EpisodeState) -> EpisodeState:
        """The node "write": the chapter becomes a script."""
        answer = ask(write_step.INSTRUCTIONS, state["chapter"], write_step.Script)
        return {
            "script": answer.parsed.sentences,
            "costs": [_cost("write", answer)],
        }

    def check(state: EpisodeState) -> EpisodeState:
        """The node "check": the script is checked against the chapter."""
        text = check_step.numbered_texts(state["chapter"], state["script"])
        answer = ask(check_step.INSTRUCTIONS, text, check_step.Flags)
        return {
            "flags": answer.parsed.flags,
            "costs": [_cost("check", answer)],
        }

    def check_the_flags(state: EpisodeState) -> EpisodeState:
        """The node "guard": plain code checks every flag of the checker."""
        return {
            "checked": guard.check_flags(
                state["chapter"], state["script"], state["flags"]
            )
        }

    builder = StateGraph(EpisodeState)
    builder.add_node("write", write, retry_policy=retry)
    builder.add_node("check", check, retry_policy=retry)
    # No retry policy: the guard asks nobody, so a second try would give the
    # same result.
    builder.add_node("guard", check_the_flags)
    builder.add_edge(START, "write")
    builder.add_edge("write", "check")
    builder.add_edge("check", "guard")
    builder.add_edge("guard", END)
    # "compile" checks the description and makes the thing that can run.
    return builder.compile()


def run_episode(chapter: str, ask: Ask, retry: RetryPolicy = RETRY) -> EpisodeState:
    """One run of the graph, from the chapter to the last state."""
    last_state = build_graph(ask, retry).invoke({"chapter": chapter})
    # LangGraph types this answer of "invoke" as a dictionary of anything.
    # It is our state.
    return cast(EpisodeState, last_state)


def picture() -> str:
    """The graph as the text of a Mermaid diagram, printed by LangGraph."""

    def never_asked[Shape: BaseModel](
        instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        raise AssertionError("drawing the graph asks no model")

    return build_graph(never_asked).get_graph().draw_mermaid()


def _cost(step: str, answer: ModelAnswer[object]) -> Cost:
    return Cost(
        step=step,
        tokens_in=answer.tokens_in,
        tokens_out=answer.tokens_out,
        thinking_tokens=answer.thinking_tokens,
        seconds=answer.seconds,
    )
